import { useState } from 'react';

export default function HumanInputPanel({
  request,
  onSubmit,
}: {
  request: { message: string; input_type: string } | null;
  onSubmit: (text: string) => void;
}) {
  const [response, setResponse] = useState('');

  if (!request) {
    return (
      <div className="border rounded-lg p-4 bg-gray-50 opacity-60">
        <p className="text-sm text-gray-500">Waiting for agent request...</p>
        <input disabled className="mt-2 w-full border rounded px-3 py-1 text-sm" />
        <button disabled className="mt-2 px-3 py-1 bg-gray-300 rounded text-sm">Submit</button>
      </div>
    );
  }

  return (
    <div className="border rounded-lg p-4 bg-yellow-50 shadow-sm">
      <div className="font-medium text-sm mb-1 text-yellow-800">Input Required</div>
      <div className="text-sm mb-3">{request.message}</div>
      <textarea
        className="w-full border rounded px-3 py-2 text-sm min-h-[80px]"
        placeholder="Your response..."
        value={response}
        onChange={(e) => setResponse(e.target.value)}
      />
      <div className="mt-2 flex gap-2">
        <button
          className="px-4 py-1 bg-yellow-600 text-white rounded text-sm"
          onClick={() => { onSubmit(response); setResponse(''); }}
        >Submit</button>
      </div>
    </div>
  );
}
