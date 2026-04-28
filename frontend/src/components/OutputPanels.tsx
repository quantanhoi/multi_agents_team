export function OutputPanels({ planOutput, coderOutputs, testReports }: {
  planOutput: any; coderOutputs: any[]; testReports: any[];
}) {
  return (
    <div className="grid grid-cols-3 gap-4 mt-4">
      <div className="border rounded-lg p-3 max-h-96 overflow-y-auto">
        <h4 className="font-semibold text-sm mb-2 text-blue-700">PLAN</h4>
        <pre className="text-xs whitespace-pre-wrap">{planOutput ? JSON.stringify(planOutput, null, 2) : 'Waiting...'}</pre>
      </div>
      <div className="border rounded-lg p-3 max-h-96 overflow-y-auto">
        <h4 className="font-semibold text-sm mb-2 text-green-700">CODER OUTPUT</h4>
        {coderOutputs.length === 0 ? <p className="text-xs text-gray-400">Waiting...</p> : (
          coderOutputs.map((o, i) => (
            <div key={i} className="mb-2 border-b pb-2 text-xs">
              <p className="font-medium">{o.summary || 'Iteration ' + (i + 1)}</p>
              <pre className="text-xs whitespace-pre-wrap mt-1 bg-gray-50 p-2 rounded">{JSON.stringify(o, null, 2)}</pre>
            </div>
          ))
        )}
      </div>
      <div className="border rounded-lg p-3 max-h-96 overflow-y-auto">
        <h4 className="font-semibold text-sm mb-2 text-orange-700">TEST REPORT</h4>
        {testReports.length === 0 ? <p className="text-xs text-gray-400">Waiting...</p> : (
          testReports.map((r, i) => (
            <div key={i} className="mb-2 border-b pb-2 text-xs">
              <span className={`px-1.5 py-0.5 rounded text-xs font-bold ${r.status === 'pass' ? 'bg-green-200 text-green-800' : 'bg-red-200 text-red-800'}`}>
                {r.status?.toUpperCase()}
              </span>
              <pre className="text-xs whitespace-pre-wrap mt-1 bg-gray-50 p-2 rounded">{JSON.stringify(r, null, 2)}</pre>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
