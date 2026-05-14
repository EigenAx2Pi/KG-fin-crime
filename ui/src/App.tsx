import { useState } from 'react'
import { PipelineHeader } from '@/components/PipelineHeader'
import { FindingsList } from '@/components/FindingsList'
import { FindingDetailPane } from '@/components/FindingDetailPane'

export default function App() {
  const [selectedId, setSelectedId] = useState<number | null>(null)

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <PipelineHeader />
      <main className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[minmax(340px,380px)_1fr]">
        <FindingsList selectedId={selectedId} onSelect={setSelectedId} />
        <section className="min-h-0 overflow-hidden">
          <FindingDetailPane findingId={selectedId} />
        </section>
      </main>
    </div>
  )
}
