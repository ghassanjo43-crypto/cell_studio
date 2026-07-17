// First-run "Workspace tips" overlay.

export function OnboardingTips({ onClose }: { onClose: () => void }) {
  return (
    <div className="onboard-overlay" onClick={onClose}>
      <div className="onboard-card" onClick={(e) => e.stopPropagation()}>
        <h2>Welcome to the Cell Explorer workspace</h2>
        <p className="muted">A quick tour of your scientific workstation:</p>
        <ul className="onboard-list">
          <li><span>🖱️</span><div><b>Rotate & zoom</b> — drag to orbit the cell, scroll to zoom from the whole cell down to the genome.</div></li>
          <li><span>🔬</span><div><b>Inspect structures</b> — hover any structure for live values; click it to open the Inspector in the right panel.</div></li>
          <li><span>⏱️</span><div><b>Timeline replay</b> — scrub the bottom dock, jump to events, or press <kbd>Space</kbd> to play/pause.</div></li>
          <li><span>◈</span><div><b>AI Copilot</b> — open it in the right panel to ask grounded questions about the run.</div></li>
          <li><span>⛶</span><div><b>Full screen</b> — the ⛶ button on the toolbar (press <kbd>Esc</kbd> to exit).</div></li>
          <li><span>⌘</span><div><b>Command palette</b> — press <kbd>Ctrl / ⌘ + K</kbd> to search and run any action.</div></li>
        </ul>
        <button className="btn btn-primary" onClick={onClose}>Got it — start exploring</button>
      </div>
    </div>
  );
}
