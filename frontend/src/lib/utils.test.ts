import { describe, expect, it } from "vitest";
import { cn } from "./utils";

describe("cn (Tailwind class merger)", () => {
  it("should concatenate simple strings", () => {
    expect(cn("foo", "bar")).toBe("foo bar");
  });

  it("should handle conditional classes", () => {
    const isActive = false;
    expect(cn("foo", isActive && "bar", "baz")).toBe("foo baz");
  });

  it("should handle objects with boolean values", () => {
    expect(cn({ foo: true, bar: false, baz: true })).toBe("foo baz");
  });

  it("should handle arrays of classes", () => {
    expect(cn(["foo", "bar"], "baz")).toBe("foo bar baz");
  });

  it("should merge conflicting Tailwind classes (later wins)", () => {
    // twMerge résout les conflits : p-4 p-6 → p-6
    expect(cn("p-4", "p-6")).toBe("p-6");
  });

  it("should merge conflicting Tailwind color classes", () => {
    expect(cn("text-red-500", "text-blue-500")).toBe("text-blue-500");
  });

  it("should preserve non-conflicting classes", () => {
    expect(cn("text-red-500", "bg-white", "p-4")).toBe("text-red-500 bg-white p-4");
  });

  it("should handle empty and undefined values", () => {
    expect(cn("foo", undefined, null, "", "bar")).toBe("foo bar");
  });

  it("should return empty string for no arguments", () => {
    expect(cn()).toBe("");
  });
});
