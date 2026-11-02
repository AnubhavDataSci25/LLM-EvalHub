export function DocTable({ headers = [], rows = [], caption, className = '' }) {
  return (
    <div className={`my-6 space-y-2 ${className}`}>
      {caption && <p className="text-xs font-semibold uppercase tracking-wider text-faint">{caption}</p>}
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              {headers.map((h, i) => (
                <th key={i}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, rIdx) => (
              <tr key={rIdx}>
                {row.map((cell, cIdx) => (
                  <td key={cIdx}>
                    {typeof cell === 'string' && cell.startsWith('`') && cell.endsWith('`') ? (
                      <code className="mono rounded bg-overlay px-1.5 py-0.5 text-xs text-accent">
                        {cell.slice(1, -1)}
                      </code>
                    ) : (
                      cell
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
