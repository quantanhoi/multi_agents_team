import { useState } from 'react';

export function HumanInputModal({ message, requestedBy, inputType, onSubmit }: {
  message: string; requestedBy: string; inputType: string; onSubmit: (text: string, files: string[]) => Promise<void>;
}) {
  const [text, setText] = useState('');
  const [files, setFiles] = useState('');
  const [loading, setLoading] = useState(false);

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-xl p-6 w-full max-w-md">
        <h3 className="text-lg font-bold mb-2 text-yellow-700">Human Input Required</h3>
        <p className="text-sm text-gray-500 mb-2">Requested by: <strong>{requestedBy}</strong> ({inputType})</p>
        <p className="text-sm mb-4 p-3 bg-yellow-50 rounded-lg">{message}</p>
        <textarea className="border rounded w-full px-3 py-2 text-sm mb-2" rows={3} value={text} onChange={e => setText(e.target.value)} placeholder="Your response..." />
        <input className="border rounded w-full px-3 py-2 text-sm mb-4" value={files} onChange={e => setFiles(e.target.value)} placeholder="File paths (comma-separated)" />
        <div className="flex justify-end gap-2">
          <button onClick={async () => { setLoading(true); await onSubmit(text, files.split(',').map(f => f.trim()).filter(Boolean)); setLoading(false); }} disabled={loading} className="px-4 py-2 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 disabled:opacity-50">
            {loading ? 'Submitting...' : 'Submit & Resume'}
          </button>
        </div>
      </div>
    </div>
  );
}
