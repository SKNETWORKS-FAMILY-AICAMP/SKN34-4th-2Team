import type { TableData } from './pythonProtocol';

/** 결과 표(DataFrame · SQL 조회) — 앞 50행까지. 글자로만 그린다. 노트북 셀과 SQL 문제 셀이 같이 쓴다 */
export function OutputTable({ table, label }: { table: TableData; label: string }) {
  const [rows, cols] = table.shape;
  return (
    <div className="py-nb-table">
      <span className="py-nb-out__label">{label}</span>
      <div className="py-nb-table__scroll">
        <table>
          <thead>
            <tr>
              <th>{table.indexName}</th>
              {table.columns.map((c, i) => (
                <th key={i}>{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {table.rows.map((row, r) => (
              <tr key={r}>
                <th>{table.index[r]}</th>
                {row.map((v, c) => (
                  <td key={c}>{v}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <span className="py-nb-table__shape">
        {rows}행 × {cols}열{rows > table.rows.length ? ` · 앞 ${table.rows.length}행만 표시` : ''}
      </span>
    </div>
  );
}
