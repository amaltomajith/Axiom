/**
 * Turn bare evidence markers like "[T3]" into markdown links "[T3](#ev-T3)" so the renderer can show
 * them as clickable citation chips. Markers that are already links are left untouched.
 */
export function linkCitations(markdown: string): string {
  return markdown.replace(/\[(T\d+)\](?!\()/g, '[$1](#ev-$1)');
}

export function citationId(href: string | undefined): string | null {
  const m = href?.match(/^#ev-(T\d+)$/);
  return m ? m[1] : null;
}
