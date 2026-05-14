import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { METHOD_LABELS, METHOD_DESC, type MethodType } from '../../data/algorithms'
import { getMethodFiles } from '../../api/algorithms'

const METHOD_ORDER: MethodType[] = [
  'official_api',
  'unofficial_api',
  'http_requests',
  'headless_browser',
  'classical_browser',
]

const WRAPPER_CODE = `from app.algorithm.methods import MethodWrapper\n\n\nclass RedditDataAlgorithm:\n    def __init__(self, method_type: str = "official"):\n        self.actions = MethodWrapper(method_type)\n\n    def run(self, subreddit: str, limit: int = 10):\n        return self.actions.get_post(subreddit, limit=limit)`

export default function AlgorithmPage() {
  const [method, setMethod] = useState<MethodType>('official_api')
  const { data = {}, isLoading } = useQuery({
    queryKey: ['algorithm-method-files'],
    queryFn: getMethodFiles,
  })

  const files = useMemo(() => data[method] ?? [], [data, method])

  return (
    <div className="flex gap-5 min-h-0">
      <aside className="w-56 shrink-0 space-y-4">
        <div>
          <p className="text-xs text-gray-600 uppercase tracking-wider px-2 pb-2">Platform</p>
          <div className="rounded-lg border border-brand-600/40 bg-brand-500/10 px-3 py-2 text-sm font-medium text-brand-400">
            reddit
          </div>
        </div>
        <div>
          <p className="text-xs text-gray-600 uppercase tracking-wider px-2 pb-2">Method Type</p>
          <div className="space-y-1">
            {METHOD_ORDER.map(m => (
              <button
                key={m}
                onClick={() => setMethod(m)}
                className={`w-full text-left px-3 py-2 rounded-lg text-xs transition-colors ${
                  method === m ? 'bg-brand-600/20 text-brand-400 font-medium' : 'text-gray-500 hover:text-gray-200 hover:bg-gray-700/40'
                }`}
              >
                <p className="font-medium">{METHOD_LABELS[m]}</p>
                <p className={`mt-0.5 leading-tight ${method === m ? 'text-brand-500/70' : 'text-gray-700'}`}>{METHOD_DESC[m]}</p>
              </button>
            ))}
          </div>
        </div>
      </aside>

      <div className="flex-1 min-w-0 space-y-5">
        <div className="rounded-xl border border-gray-700/50 bg-gray-800/30 overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-700/30">
            <p className="text-sm font-semibold text-gray-100">Wrapper Pattern</p>
            <p className="text-xs text-gray-500 mt-0.5">Algorithm calls wrapper, wrapper injects file-based methods by method type.</p>
          </div>
          <pre className="px-4 py-3 font-mono text-xs text-gray-300 whitespace-pre overflow-x-auto">{WRAPPER_CODE}</pre>
        </div>

        

        {isLoading ? (
          <div className="rounded-xl border border-gray-700/50 bg-gray-800/30 p-4 text-sm text-gray-500">Loading files...</div>
        ) : files.length === 0 ? (
          <div className="rounded-xl border border-dashed border-gray-700/50 p-4 text-sm text-gray-500">No files found for this method type.</div>
        ) : (
          <div className="space-y-3">
            {files.map(file => (
              <div key={file.path} className="rounded-xl border border-gray-700/50 bg-gray-800/30 overflow-hidden">
                <div className="px-4 py-3 border-b border-gray-700/30">
                  <p className="font-mono text-sm font-semibold text-gray-100">{file.name}</p>
                  <p className="text-xs text-gray-500 mt-0.5">{file.path}</p>
                </div>
                <pre className="px-4 py-3 font-mono text-xs text-gray-300 whitespace-pre overflow-x-auto">{file.content}</pre>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
