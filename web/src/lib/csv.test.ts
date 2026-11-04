import { describe, expect, it } from "vitest";

import { toCsv } from "./csv";

describe("csv", () => {
  it("quotes commas, quotes and newlines", () => {
    expect(toCsv(["a", "b"], [["x,y", 'say "hi"'], ["line\nbreak", null]])).toBe(
      'a,b\r\n"x,y","say ""hi"""\r\n"line\nbreak",\r\n',
    );
  });

  it("defuses spreadsheet formulas in text but not in numbers", () => {
    expect(toCsv(["v"], [["=HYPERLINK(\"x\")"], ["@SUM(A1)"], [-3.5]])).toBe(
      'v\r\n"\'=HYPERLINK(""x"")"\r\n\'@SUM(A1)\r\n-3.5\r\n',
    );
  });
});
