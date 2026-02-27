type ScreenshotModalProps = {
  src: string | null
  onClose: () => void
}

export function ScreenshotModal({ src, onClose }: ScreenshotModalProps) {
  if (!src) {
    return null
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-6" onClick={onClose}>
      <div className="max-h-[80vh] max-w-[80vw] overflow-hidden rounded-2xl bg-white shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <img src={src} alt="Screenshot" className="h-full w-full object-contain" />
        <button
          type="button"
          onClick={onClose}
          className="w-full border-t border-fog-200 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-ink-700"
        >
          Close
        </button>
      </div>
    </div>
  )
}
