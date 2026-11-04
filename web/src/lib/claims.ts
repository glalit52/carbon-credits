import type { ClaimBasis, RetirementPurpose } from "@/lib/database.types";

// Plain-language versions of what claim_basis() returns, for buyers. The
// wording follows carbonstack.article6.ClaimStatus.buyer_language.

export const PURPOSE_LABEL: Record<RetirementPurpose, string> = {
  contribution: "Contribution",
  offset: "Offset against own target",
  corsia: "CORSIA",
};

export function buyerLanguage(c: ClaimBasis | undefined, country: string | null): string {
  const host = country ?? "the host country";
  if (!c || c.offsettable_credits <= 0) {
    if (c?.basis === "authorised_itmo") {
      return `Authorised for transfer, but ${host} has not applied a corresponding adjustment yet. Until it does, these credits may be described as financed reductions only, not counted against a buyer's own target.`;
    }
    return `Financed emission reductions in ${host}. ${host} still counts these tonnes toward its own climate target, so a buyer may not count them against theirs.`;
  }
  return `${c.offsettable_credits} credit${c.offsettable_credits === 1 ? "" : "s"} have a corresponding adjustment behind them and may be counted against a buyer's own target${c.corsia_eligible ? " or used under CORSIA" : ""}. The rest may only be described as financed.`;
}
