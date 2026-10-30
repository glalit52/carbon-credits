"use client";

import { Button } from "@/components/ui";

export function PrintButton() {
  return (
    <Button type="button" variant="secondary" onClick={() => window.print()}>
      Print or save as PDF
    </Button>
  );
}

/** The same, with its label in the reader's language, and hidden on paper. */
export function PrintLabel({ label }: { label: string }) {
  return (
    <Button type="button" variant="secondary" className="print:hidden" onClick={() => window.print()}>
      {label}
    </Button>
  );
}
