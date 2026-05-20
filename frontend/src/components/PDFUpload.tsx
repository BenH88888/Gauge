import { useRef, useState } from "react";
import { DocumentMeta, uploadPDF } from "../api";

interface PDFUploadProps {
  onUploaded: (doc: DocumentMeta) => void;
  disabled?: boolean;
}

export function PDFUpload({ onUploaded, disabled }: PDFUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handle(file: File) {
    setUploading(true);
    setError(null);
    try {
      const res = await uploadPDF(file);
      onUploaded(res.document);
    } catch (e) {
      setError(String(e));
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  return (
    <div>
      <input
        ref={inputRef}
        type="file"
        accept="application/pdf,.pdf"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) void handle(f);
        }}
      />
      <button
        type="button"
        disabled={disabled || uploading}
        onClick={() => inputRef.current?.click()}
        className="rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-brand-700 disabled:cursor-not-allowed disabled:bg-slate-300"
      >
        {uploading ? "Uploading..." : "Upload a plan PDF"}
      </button>
      {error && (
        <div className="mt-2 rounded bg-red-50 px-3 py-2 text-xs text-red-700">
          {error}
        </div>
      )}
    </div>
  );
}
