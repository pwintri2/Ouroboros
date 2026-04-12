export function StreamStatusCard() {
  return (
    <div className="rounded-[16px] border border-[#ccb28c] bg-[#f7efdf] p-3">
      <div className="tech-label">Streaming / Sandbox</div>
      <div className="mt-2 text-sm text-[#4b3923]">
        SSE kanaal voorbereid. Deze zone wordt gebruikt voor live discussie, sandbox streaming en observer-state updates.
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2 text-[10px] uppercase tracking-[0.16em] text-[#8b6f4c]">
        <div className="rounded-full border border-[#ccb28c] bg-[#fff7ea] px-2 py-1 text-center">Realtime</div>
        <div className="rounded-full border border-[#ccb28c] bg-[#fff7ea] px-2 py-1 text-center">Sandbox</div>
      </div>
    </div>
  )
}
