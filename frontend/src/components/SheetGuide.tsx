// The short version of docs/importing-a-spreadsheet.md, shown on the Import page,
// with a template file to start from. Everything here works offline.

const TEMPLATE = [
  "Date,Account,Category,Subcategory,Payee,Amount,Notes",
  "2023-01-03,Checking,Income,Salary,Acme Corp,2500.00,",
  "2023-01-05,Visa,Food,Groceries,Corner Market,-84.12,",
  "2023-01-06,Visa,Food,Coffee,Blue Bottle,-4.75,oat latte",
  "2023-01-10,Checking,Housing,Rent,Landlord,-1200.00,January rent",
].join("\r\n");

function downloadTemplate() {
  // A file made in the browser: a Blob, given a temporary URL, clicked as a download link.
  const url = URL.createObjectURL(new Blob([TEMPLATE], { type: "text/csv" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = "finance-import-template.csv";
  link.click();
  URL.revokeObjectURL(url);
}

export function SheetGuide() {
  return (
    <details className="sheet-guide">
      <summary>How to get your spreadsheet ready</summary>
      <ol>
        <li>
          <b>One header row, then one transaction per row.</b> Delete title rows, total and subtotal rows, blank
          spacer rows, and unmerge any merged cells.
        </li>
        <li>
          <b>These columns</b> (any order, any names; you match them in step 2): Date, Account, Category,
          Subcategory, Payee, Amount, Notes. Only Date and Amount are required. “Food &gt; Coffee” in one Category
          cell works too.
        </li>
        <li>
          <b>Dates</b> like 2023-01-05 or 1/5/2023 (month first). If Excel shows ##### or a number like 44931, format
          the column as a Date.
        </li>
        <li>
          <b>Amounts</b> as plain numbers: negative for money out, positive for money in. If every amount is
          positive, pick “Category decides” in step 2 and income categories count as money in.
        </li>
        <li>
          <b>Leave out moves between your own accounts</b> (card payments, savings transfers). Imported as spending
          they would count twice. Add them as transfers in the app afterwards.
        </li>
        <li>
          <b>In Excel:</b> File › Save As › <i>CSV UTF-8 (Comma delimited)</i>. Only the sheet you're on is saved.
        </li>
      </ol>
      <p className="muted">
        <button type="button" className="btn small" onClick={downloadTemplate}>
          Download a template
        </button>{" "}
        The full guide, with Excel formulas for common fixes, is in docs/importing-a-spreadsheet.md.
      </p>
    </details>
  );
}
