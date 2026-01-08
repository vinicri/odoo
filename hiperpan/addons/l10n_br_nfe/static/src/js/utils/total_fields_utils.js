export const getItemsWithNonZeroValue = (record, field) => {
  if (!record || !record.data) {
      return [];
  }

  const invoiceLines = record.data.invoice_line_ids;
  if (!invoiceLines || !invoiceLines.records) {
      return [];
  }


  const recordsWithNonZeroValue = [];
  for (const line of invoiceLines.records) {
      const value = line.data[field] || 0;
      if (value > 0) {
          recordsWithNonZeroValue.push(line);
      }
  }
  return recordsWithNonZeroValue;
}