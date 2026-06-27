// score by fields
// in descending order of importance
function scoreFields(query, orderedFields) {
  const words = query.toLowerCase().trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return 0;

  const lowerFields = orderedFields.map(f => (f || '').toLowerCase());
  // weight decreases by position: first field is most important
  const weights = lowerFields.map((_, i) => lowerFields.length - i);

  let score = 0;
  let anyMatched = false;
  // OR scoring, one word match is always enough
  // each extra matching word gives extra points
  for (const word of words) {
    for (let i = 0; i < lowerFields.length; i++) {
      if (lowerFields[i].includes(word)) {
        score += weights[i];
        anyMatched = true;
        break; // count each word once, at its highest-priority field
      }
    }
  }
  return anyMatched ? score : -1;
}

// abstract search
// getting the fields to search in
// in descending order of importance
// scoring each item by that
// filtering out those that dont match query in any field
// sorting by score then by alphabet by most important field
function search(query, items, getFields) {
  return items
    .map((item) => {
      const fields = getFields(item);
      return {
        item,
        fields,
        score: scoreFields(query, fields)
      }
    })
    .filter(s => s.score >= 0)
    .sort((a, b) => {
      if (b.score !== a.score) {
        return b.score - a.score;
      }
      return a.fields[0].localeCompare(b.fields[0], "de")
    })
    .map((result) => result.item)
}
