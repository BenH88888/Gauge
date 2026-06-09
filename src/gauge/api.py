"""Unified FastAPI application factory.

The factory takes the benefits-side ``CatalogRepository``, a fitted
``CostPredictor``, and the session / extraction dependencies, then wires
everything onto a single app. Tests inject fresh dependencies per case via
FastAPI's dependency-override mechanism.
"""

from __future__ import annotations

import os
import uuid
from typing import Literal

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from gauge.benefits.calculator import estimate_cost_share
from gauge.benefits.models import (
    EstimateRequest,
    EstimateResult,
    Member,
    Plan,
    Procedure,
    ServiceCategory,
)
from gauge.benefits.repository import CatalogRepository
from gauge.docchat.schemas import (
    ChatRequest,
    ChatResponse,
    ChatTurn,
    DocumentMeta,
    UploadResponse,
)
from gauge.docchat.service import DocumentChatService
from gauge.plan_extract.extractor import PlanExtractor
from gauge.plan_extract.schemas import PlanDraft
from gauge.predictor.annual_cost import OopInterval, oop_interval_from_prediction
from gauge.predictor.model import CostPrediction, CostPredictor
from gauge.predictor.schemas import PredictionFeatures
from gauge.predictor.whatif import (
    SWEEPABLE_FEATURES,
    SweepValue,
    WhatIfResponse,
    sweep,
)
from gauge.session.models import (
    AttachDocumentResponse,
    ConfirmPlanRequest,
    CreateSessionRequest,
    CreateSessionResponse,
    Session,
    SessionEstimate,
)
from gauge.saved_estimates.models import (
    InMemorySavedEstimateStore,
    SavedEstimate,
    SavedEstimateStore,
)
from gauge.session.store import InMemorySessionStore, SessionStore


class PredictRequest(BaseModel):
    """POST /predict body."""

    features: PredictionFeatures
    plan_id: str | None = None


class SessionWhatIfRequest(BaseModel):
    """POST /sessions/{id}/whatif body."""

    feature: str
    values: list[SweepValue]


class SessionChatRequest(BaseModel):
    """POST /sessions/{id}/chat body.

    A slimmer alternative to ``ChatRequest`` — the session already knows
    its ``document_id``, so the client does not need to supply it.
    """

    question: str = Field(min_length=1, max_length=2_000)
    history: list[ChatTurn] = Field(
        default_factory=list,
        description="Prior turns in this conversation, oldest first.",
    )
    top_k: int = Field(default=4, ge=1, le=20)


class PredictResponse(BaseModel):
    """POST /predict response.

    Parameters
    ----------
    prediction : CostPrediction
        Raw ML prediction: median, mean, and 80 % conformal charge interval.
    oop_interval : OopInterval or None
        Conformal OOP interval derived by propagating ``prediction`` through
        the requested plan. ``None`` when no ``plan_id`` was supplied.
    """

    prediction: CostPrediction
    oop_interval: OopInterval | None = None


class SaveEstimateRequest(BaseModel):
    """POST /saved-estimates body."""

    session_id: str
    label: str = Field(min_length=1, max_length=120)


class RenameEstimateRequest(BaseModel):
    """PATCH /saved-estimates/{id} body."""

    label: str = Field(min_length=1, max_length=120)


class WhatIfRequest(BaseModel):
    """POST /whatif body."""

    baseline: PredictionFeatures
    feature: Literal["age", "sex", "bmi", "children", "smoker", "region"]
    values: list[SweepValue]
    plan_id: str | None = None


MAX_PDF_BYTES = 25 * 1024 * 1024  # 25 MB upload cap


def create_app(
    repository: CatalogRepository,
    predictor: CostPredictor,
    chat_service: DocumentChatService | None = None,
    session_store: SessionStore | None = None,
    plan_extractor: PlanExtractor | None = None,
    saved_estimate_store: SavedEstimateStore | None = None,
) -> FastAPI:
    """Build a FastAPI app wired to the supplied dependencies.

    Parameters
    ----------
    repository : CatalogRepository
        Catalog source for plans, members, and procedures.
    predictor : CostPredictor
        A *fitted* predictor. Callers are responsible for training or
        loading the model before constructing the app.
    chat_service : DocumentChatService or None, optional
        Document-chat orchestrator. A fresh instance is created when not
        supplied; tests can inject their own.
    session_store : SessionStore or None, optional
        Store for the guided-flow sessions. A fresh instance is created
        when not supplied.
    plan_extractor : PlanExtractor or None, optional
        LLM-powered plan field extractor. When ``None`` the extractor is
        constructed from the ``chat_service``'s LLM backend.

    Returns
    -------
    FastAPI
        A configured FastAPI instance ready to be served or wrapped in a
        ``TestClient``.

    Raises
    ------
    ValueError
        If ``predictor`` has not been fitted yet.
    """
    if not predictor.is_fitted:
        raise ValueError("CostPredictor must be fitted before being passed to create_app.")

    chat_service = chat_service or DocumentChatService()
    session_store = session_store or InMemorySessionStore()
    plan_extractor = plan_extractor or PlanExtractor(llm=chat_service.llm)
    _saved_estimate_store = saved_estimate_store or InMemorySavedEstimateStore()

    def get_saved_estimate_store() -> SavedEstimateStore:
        return _saved_estimate_store

    def get_user_id(
        x_gauge_user_id: str = Header(
            ...,
            description=(
                "Anonymous user identity generated by the browser. "
                "Must be a non-empty string sent as the X-Gauge-User-Id header."
            ),
        ),
    ) -> str:
        """Extract the caller's anonymous identity from the request header.

        Parameters
        ----------
        x_gauge_user_id : str
            Value of the ``X-Gauge-User-Id`` HTTP header.  FastAPI
            automatically maps the hyphenated header name to this
            underscore parameter.

        Returns
        -------
        str
            The caller's user ID.

        Raises
        ------
        HTTPException
            422 if the header is absent (FastAPI default for a required Header).
        """
        return x_gauge_user_id

    app = FastAPI(
        title="Gauge",
        version="0.2.0",
        description="Calibrated out-of-pocket cost estimation with honest uncertainty bounds.",
    )

    # CORS for the React dev server. Default allows the standard Vite
    # ports; tighten or override via GAUGE_CORS_ORIGINS in production.
    raw_origins = os.environ.get(
        "GAUGE_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    )
    allowed_origins = [o.strip() for o in raw_origins.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["*"],
    )

    def get_repository() -> CatalogRepository:
        return repository

    def get_predictor() -> CostPredictor:
        return predictor

    def get_chat_service() -> DocumentChatService:
        return chat_service

    def get_session_store() -> SessionStore:
        return session_store

    def get_plan_extractor() -> PlanExtractor:
        return plan_extractor

    @app.get("/healthz", tags=["meta"])
    def healthz() -> dict[str, str]:
        """Return ``{"status": "ok"}`` for liveness checks."""
        return {"status": "ok"}

    # --- benefits routes -------------------------------------------------

    @app.get("/plans/{plan_id}", response_model=Plan, tags=["catalog"])
    def get_plan(
        plan_id: str,
        repo: CatalogRepository = Depends(get_repository),
    ) -> Plan:
        """Return the plan matching ``plan_id``, or 404 if not found."""
        plan = repo.get_plan(plan_id)
        if plan is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Plan '{plan_id}' not found.",
            )
        return plan

    @app.get("/members/{member_id}", response_model=Member, tags=["catalog"])
    def get_member(
        member_id: str,
        repo: CatalogRepository = Depends(get_repository),
    ) -> Member:
        """Return the member matching ``member_id``, or 404 if not found."""
        member = repo.get_member(member_id)
        if member is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Member '{member_id}' not found.",
            )
        return member

    @app.get("/procedures/{code}", response_model=Procedure, tags=["catalog"])
    def get_procedure(
        code: str,
        repo: CatalogRepository = Depends(get_repository),
    ) -> Procedure:
        """Return the procedure matching ``code``, or 404 if not found."""
        proc = repo.get_procedure(code)
        if proc is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Procedure '{code}' not found.",
            )
        return proc

    @app.post(
        "/estimate",
        response_model=EstimateResult,
        tags=["estimate"],
    )
    def post_estimate(
        request: EstimateRequest,
        repo: CatalogRepository = Depends(get_repository),
    ) -> EstimateResult:
        """Compute an out-of-pocket estimate for a single procedure."""
        member = repo.get_member(request.member_id)
        if member is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Member '{request.member_id}' not found.",
            )
        plan = repo.get_plan(member.plan_id)
        if plan is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(f"Plan '{member.plan_id}' for member '{member.member_id}' not found."),
            )
        procedure = repo.get_procedure(request.procedure_code)
        if procedure is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Procedure '{request.procedure_code}' not found.",
            )
        return estimate_cost_share(
            plan=plan,
            member=member,
            procedure=procedure,
            in_network=request.in_network,
        )

    # --- predictor routes ------------------------------------------------

    @app.post(
        "/predict",
        response_model=PredictResponse,
        tags=["predictor"],
    )
    def post_predict(
        request: PredictRequest,
        model: CostPredictor = Depends(get_predictor),
        repo: CatalogRepository = Depends(get_repository),
    ) -> PredictResponse:
        """Predict annual medical charges; optionally annotate with plan OOP interval."""
        prediction = model.predict(request.features)
        interval = _oop_interval_for(request.plan_id, prediction, repo)
        return PredictResponse(prediction=prediction, oop_interval=interval)

    @app.post(
        "/whatif",
        response_model=WhatIfResponse,
        tags=["predictor"],
    )
    def post_whatif(
        request: WhatIfRequest,
        model: CostPredictor = Depends(get_predictor),
        repo: CatalogRepository = Depends(get_repository),
    ) -> WhatIfResponse:
        """Vary one feature across values and return the prediction curve."""
        if request.feature not in SWEEPABLE_FEATURES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot sweep '{request.feature}'.",
            )
        plan = _resolve_plan(request.plan_id, repo)
        try:
            return sweep(
                predictor=model,
                baseline=request.baseline,
                feature=request.feature,
                values=request.values,
                plan=plan,
            )
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    # --- document chat routes ------------------------------------------

    @app.post(
        "/documents",
        response_model=UploadResponse,
        tags=["docchat"],
    )
    async def post_document(
        file: UploadFile = File(...),
        service: DocumentChatService = Depends(get_chat_service),
    ) -> UploadResponse:
        """Upload a PDF and build a retrieval index over it."""
        if file.content_type not in (
            "application/pdf",
            "application/x-pdf",
            None,
        ) and not (file.filename or "").lower().endswith(".pdf"):
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Only PDF uploads are accepted.",
            )
        contents = await file.read()
        if not contents:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty.",
            )
        if len(contents) > MAX_PDF_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"PDF exceeds {MAX_PDF_BYTES // (1024 * 1024)} MB cap.",
            )
        try:
            meta = service.upload_pdf(
                filename=file.filename or "uploaded.pdf",
                pdf_bytes=contents,
            )
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
        return UploadResponse(document=meta)

    @app.get(
        "/documents",
        response_model=list[DocumentMeta],
        tags=["docchat"],
    )
    def list_documents(
        service: DocumentChatService = Depends(get_chat_service),
    ) -> list[DocumentMeta]:
        """Return metadata for all currently stored documents."""
        return service.store.list_meta()

    @app.delete(
        "/documents/{document_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        tags=["docchat"],
    )
    def delete_document(
        document_id: str,
        service: DocumentChatService = Depends(get_chat_service),
    ) -> None:
        """Delete a document by ID; returns 404 if not found."""
        if not service.store.delete(document_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document '{document_id}' not found.",
            )

    @app.post(
        "/chat",
        response_model=ChatResponse,
        tags=["docchat"],
    )
    def post_chat(
        request: ChatRequest,
        service: DocumentChatService = Depends(get_chat_service),
    ) -> ChatResponse:
        """Answer a question against a previously uploaded document."""
        try:
            return service.ask(
                document_id=request.document_id,
                question=request.question,
                top_k=request.top_k,
            )
        except KeyError as e:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document '{request.document_id}' not found.",
            ) from e

    # --- guided session routes -------------------------------------------

    @app.post(
        "/sessions",
        response_model=CreateSessionResponse,
        tags=["session"],
    )
    def post_create_session(
        request: CreateSessionRequest,
        model: CostPredictor = Depends(get_predictor),
        store: SessionStore = Depends(get_session_store),
    ) -> CreateSessionResponse:
        """Create a session from user demographics and return a first-pass prediction.

        Parameters
        ----------
        request : CreateSessionRequest
            User's demographic inputs.
        model : CostPredictor
            Injected fitted predictor.
        store : SessionStore
            Injected session store.

        Returns
        -------
        CreateSessionResponse
            New session ID and the initial cost prediction (no plan context yet).
        """
        prediction = model.predict(request.features)
        session = Session(
            session_id=uuid.uuid4().hex[:16],
            features=request.features,
        )
        store.create(session)
        return CreateSessionResponse(
            session_id=session.session_id,
            prediction=prediction,
        )

    @app.post(
        "/sessions/{session_id}/document",
        response_model=AttachDocumentResponse,
        tags=["session"],
    )
    async def post_session_document(
        session_id: str,
        file: UploadFile = File(...),
        service: DocumentChatService = Depends(get_chat_service),
        extractor: PlanExtractor = Depends(get_plan_extractor),
        store: SessionStore = Depends(get_session_store),
    ) -> AttachDocumentResponse:
        """Upload a plan PDF, auto-extract fields, and attach it to the session.

        Parameters
        ----------
        session_id : str
            Session to attach the document to.
        file : UploadFile
            The PDF to upload. Must be a valid PDF under 25 MB.
        service : DocumentChatService
            Injected document chat service.
        extractor : PlanExtractor
            Injected plan extractor.
        store : SessionStore
            Injected session store.

        Returns
        -------
        AttachDocumentResponse
            The new document ID and the automatically extracted plan draft.

        Raises
        ------
        HTTPException
            404 if the session is not found; 400/413/415 for bad uploads.
        """
        session = store.get(session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session '{session_id}' not found.",
            )
        if file.content_type not in (
            "application/pdf",
            "application/x-pdf",
            None,
        ) and not (file.filename or "").lower().endswith(".pdf"):
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Only PDF uploads are accepted.",
            )
        contents = await file.read()
        if not contents:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty.",
            )
        if len(contents) > MAX_PDF_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"PDF exceeds {MAX_PDF_BYTES // (1024 * 1024)} MB cap.",
            )
        try:
            meta = service.upload_pdf(
                filename=file.filename or "plan.pdf",
                pdf_bytes=contents,
            )
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

        stored_doc = service.store.get(meta.document_id)
        draft = extractor.extract(stored_doc.index) if stored_doc is not None else PlanDraft()

        session.document_id = meta.document_id
        session.plan_draft = draft
        store.update(session)

        return AttachDocumentResponse(
            document_id=meta.document_id,
            plan_draft=draft,
        )

    @app.get(
        "/sessions/{session_id}/plan-draft",
        response_model=PlanDraft,
        tags=["session"],
    )
    def get_session_plan_draft(
        session_id: str,
        store: SessionStore = Depends(get_session_store),
    ) -> PlanDraft:
        """Return the current plan draft for a session.

        Parameters
        ----------
        session_id : str
            Target session.
        store : SessionStore
            Injected session store.

        Returns
        -------
        PlanDraft
            The current extracted (or empty) plan draft.

        Raises
        ------
        HTTPException
            404 if the session or its draft is not found.
        """
        session = store.get(session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session '{session_id}' not found.",
            )
        if session.plan_draft is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No plan draft yet -- upload a document first.",
            )
        return session.plan_draft

    @app.post(
        "/sessions/{session_id}/plan",
        response_model=SessionEstimate,
        tags=["session"],
    )
    def post_session_plan(
        session_id: str,
        request: ConfirmPlanRequest,
        model: CostPredictor = Depends(get_predictor),
        store: SessionStore = Depends(get_session_store),
    ) -> SessionEstimate:
        """Confirm plan details and return the full personalised estimate.

        Parameters
        ----------
        session_id : str
            Target session.
        request : ConfirmPlanRequest
            User-reviewed plan fields (deductible, OOP max, coinsurance,
            and optional copays).
        model : CostPredictor
            Injected fitted predictor.
        store : SessionStore
            Injected session store.

        Returns
        -------
        SessionEstimate
            Full estimate: prediction, plan breakdown for median and mean
            spend, and the confirmed plan object.

        Raises
        ------
        HTTPException
            404 if the session is not found.
        """
        session = store.get(session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session '{session_id}' not found.",
            )

        copays = {ServiceCategory(k): v for k, v in request.copays_cents.items()}
        plan = Plan(
            plan_id=uuid.uuid4().hex[:12],
            name=request.plan_name,
            deductible_cents=request.deductible_cents,
            out_of_pocket_max_cents=request.out_of_pocket_max_cents,
            coinsurance_rate=request.coinsurance_rate,
            copays_cents=copays,
        )
        session.plan = plan
        store.update(session)

        prediction = model.predict(session.features)
        return SessionEstimate(
            features=session.features,
            prediction=prediction,
            plan=plan,
            oop_interval=oop_interval_from_prediction(plan, prediction),
            document_id=session.document_id,
        )

    @app.get(
        "/sessions/{session_id}/estimate",
        response_model=SessionEstimate,
        tags=["session"],
    )
    def get_session_estimate(
        session_id: str,
        model: CostPredictor = Depends(get_predictor),
        store: SessionStore = Depends(get_session_store),
    ) -> SessionEstimate:
        """Return the current estimate for a session.

        Parameters
        ----------
        session_id : str
            Target session.
        model : CostPredictor
            Injected fitted predictor.
        store : SessionStore
            Injected session store.

        Returns
        -------
        SessionEstimate
            Current estimate.  Plan breakdown fields are ``None`` when no
            plan has been confirmed yet.

        Raises
        ------
        HTTPException
            404 if the session is not found.
        """
        session = store.get(session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session '{session_id}' not found.",
            )
        prediction = model.predict(session.features)
        interval = (
            oop_interval_from_prediction(session.plan, prediction)
            if session.plan is not None
            else None
        )
        return SessionEstimate(
            features=session.features,
            prediction=prediction,
            plan=session.plan,
            oop_interval=interval,
            document_id=session.document_id,
        )

    @app.post(
        "/sessions/{session_id}/whatif",
        response_model=WhatIfResponse,
        tags=["session"],
    )
    def post_session_whatif(
        session_id: str,
        request: SessionWhatIfRequest,
        model: CostPredictor = Depends(get_predictor),
        store: SessionStore = Depends(get_session_store),
    ) -> WhatIfResponse:
        """Run a what-if sweep using the session's demographics as the baseline.

        Parameters
        ----------
        session_id : str
            Target session.
        feature : str
            Feature to vary.
        values : list[SweepValue]
            Values to sweep the feature over.
        model : CostPredictor
            Injected fitted predictor.
        store : SessionStore
            Injected session store.

        Returns
        -------
        WhatIfResponse
            Prediction at each swept value.

        Raises
        ------
        HTTPException
            404 if the session is not found; 400 for invalid feature/values.
        """
        session = store.get(session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session '{session_id}' not found.",
            )
        if request.feature not in SWEEPABLE_FEATURES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot sweep '{request.feature}'.",
            )
        try:
            return sweep(
                predictor=model,
                baseline=session.features,
                feature=request.feature,
                values=request.values,
                plan=session.plan,
            )
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    @app.post(
        "/sessions/{session_id}/chat",
        response_model=ChatResponse,
        tags=["session"],
    )
    def post_session_chat(
        session_id: str,
        request: SessionChatRequest,
        service: DocumentChatService = Depends(get_chat_service),
        store: SessionStore = Depends(get_session_store),
    ) -> ChatResponse:
        """Answer a question against the session's uploaded plan document.

        Parameters
        ----------
        session_id : str
            Target session.
        request : ChatRequest
            Question and retrieval parameters.
        service : DocumentChatService
            Injected document chat service.
        store : SessionStore
            Injected session store.

        Returns
        -------
        ChatResponse
            Answer text and page citations.

        Raises
        ------
        HTTPException
            404 if the session or its document is not found.
        """
        session = store.get(session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session '{session_id}' not found.",
            )
        if session.document_id is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No document attached to this session yet.",
            )
        try:
            return service.ask(
                document_id=session.document_id,
                question=request.question,
                history=request.history,
                top_k=request.top_k,
            )
        except KeyError as e:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document '{session.document_id}' not found.",
            ) from e

    # --- saved estimates CRUD routes ---------------------------------------

    @app.post(
        "/saved-estimates",
        response_model=SavedEstimate,
        status_code=status.HTTP_201_CREATED,
        tags=["saved-estimates"],
    )
    def post_saved_estimate(
        request: SaveEstimateRequest,
        user_id: str = Depends(get_user_id),
        store: SessionStore = Depends(get_session_store),
        se_store: SavedEstimateStore = Depends(get_saved_estimate_store),
    ) -> SavedEstimate:
        """Save a named snapshot of the current session's estimate.

        Parameters
        ----------
        request : SaveEstimateRequest
            Session to snapshot and the label to assign it.
        user_id : str
            Caller's anonymous identity from ``X-Gauge-User-Id``.
        store : SessionStore
            Injected session store.
        se_store : SavedEstimateStore
            Injected saved-estimate store.

        Returns
        -------
        SavedEstimate
            The newly created snapshot, owned by ``user_id``.

        Raises
        ------
        HTTPException
            400 if the session has no confirmed plan yet.
            404 if the session is not found.
        """
        session = store.get(request.session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session '{request.session_id}' not found.",
            )
        if session.plan is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Session has no confirmed plan. Complete step 3 before saving.",
            )
        prediction = predictor.predict(session.features)
        oop = oop_interval_from_prediction(session.plan, prediction)
        return se_store.save(
            user_id=user_id,
            label=request.label,
            features=session.features,
            prediction=prediction,
            plan=session.plan,
            oop_interval=oop,
        )

    @app.get(
        "/saved-estimates",
        response_model=list[SavedEstimate],
        tags=["saved-estimates"],
    )
    def get_saved_estimates(
        user_id: str = Depends(get_user_id),
        se_store: SavedEstimateStore = Depends(get_saved_estimate_store),
    ) -> list[SavedEstimate]:
        """List all saved estimates owned by the caller, newest first.

        Parameters
        ----------
        user_id : str
            Caller's anonymous identity from ``X-Gauge-User-Id``.
        se_store : SavedEstimateStore
            Injected saved-estimate store.

        Returns
        -------
        list[SavedEstimate]
            Snapshots owned by ``user_id``.
        """
        return se_store.list(user_id)

    @app.patch(
        "/saved-estimates/{estimate_id}",
        response_model=SavedEstimate,
        tags=["saved-estimates"],
    )
    def patch_saved_estimate(
        estimate_id: str,
        request: RenameEstimateRequest,
        user_id: str = Depends(get_user_id),
        se_store: SavedEstimateStore = Depends(get_saved_estimate_store),
    ) -> SavedEstimate:
        """Rename a saved estimate the caller owns.

        Parameters
        ----------
        estimate_id : str
            ID of the snapshot to rename.
        request : RenameEstimateRequest
            New label.
        user_id : str
            Caller's anonymous identity from ``X-Gauge-User-Id``.

        Raises
        ------
        HTTPException
            403 if the caller does not own the snapshot.
            404 if the snapshot is not found.
        """
        try:
            return se_store.rename(estimate_id, user_id, request.label)
        except KeyError as e:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Saved estimate '{estimate_id}' not found.",
            ) from e
        except PermissionError as e:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not own this saved estimate.",
            ) from e

    @app.delete(
        "/saved-estimates/{estimate_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        tags=["saved-estimates"],
    )
    def delete_saved_estimate(
        estimate_id: str,
        user_id: str = Depends(get_user_id),
        se_store: SavedEstimateStore = Depends(get_saved_estimate_store),
    ) -> None:
        """Delete a saved estimate the caller owns.

        Parameters
        ----------
        estimate_id : str
            ID of the snapshot to remove.
        user_id : str
            Caller's anonymous identity from ``X-Gauge-User-Id``.

        Raises
        ------
        HTTPException
            403 if the caller does not own the snapshot.
            404 if the snapshot is not found.
        """
        try:
            se_store.delete(estimate_id, user_id)
        except KeyError as e:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Saved estimate '{estimate_id}' not found.",
            ) from e
        except PermissionError as e:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not own this saved estimate.",
            ) from e

    return app


def _resolve_plan(plan_id: str | None, repo: CatalogRepository) -> Plan | None:
    """Look up a plan by ID, raising HTTP 404 if provided but not found.

    Parameters
    ----------
    plan_id : str or None
        The plan identifier to look up, or ``None`` to skip the lookup.
    repo : CatalogRepository
        Catalog to query.

    Returns
    -------
    Plan or None
        The resolved plan, or ``None`` when ``plan_id`` is ``None``.

    Raises
    ------
    HTTPException
        With status 404 if ``plan_id`` is provided but not in the catalog.
    """
    if plan_id is None:
        return None
    plan = repo.get_plan(plan_id)
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plan '{plan_id}' not found.",
        )
    return plan


def _oop_interval_for(
    plan_id: str | None,
    prediction: CostPrediction,
    repo: CatalogRepository,
) -> OopInterval | None:
    """Compute the conformal OOP interval for a prediction against an optional plan.

    Parameters
    ----------
    plan_id : str or None
        Plan to evaluate against. Returns ``None`` when ``plan_id`` is ``None``.
    prediction : CostPrediction
        The charge prediction whose conformal interval is propagated.
    repo : CatalogRepository
        Catalog used to resolve the plan.

    Returns
    -------
    OopInterval or None
        Conformal OOP interval when a plan is resolved, else ``None``.

    Raises
    ------
    HTTPException
        With status 404 if ``plan_id`` is provided but not found.
    """
    plan = _resolve_plan(plan_id, repo)
    if plan is None:
        return None
    return oop_interval_from_prediction(plan, prediction)
