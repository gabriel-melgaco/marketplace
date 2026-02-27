/**
 * Tests for src/pages/public/NotFound/index.tsx
 *
 * Strategy: render the component inside a MemoryRouter (required for <Link>),
 * then assert on rendered content and navigation attributes.
 *
 * Risk level: LOW-MEDIUM
 *   - A broken 404 page creates a dead-end for lost users and harms SEO
 *     signals.  The back-to-home link must be present and correctly wired.
 *
 * Coverage matrix
 *   Rendering        : 404 text, heading, explanation paragraph
 *   Navigation link  : exists, points to "/", accessible label
 *   Accessibility    : visible text copy is correct for screen readers
 */

import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { NotFound } from "../index";

function renderNotFound(initialPath: string = "/some/missing-route") {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <NotFound />
    </MemoryRouter>,
  );
}

// ─── Rendering ────────────────────────────────────────────────────────────────

describe("NotFound - rendering", () => {
  it("displays the 404 status code prominently", () => {
    renderNotFound();
    expect(screen.getByText("404")).toBeInTheDocument();
  });

  it("displays the 'Página não encontrada' heading", () => {
    renderNotFound();
    expect(
      screen.getByText("Página não encontrada"),
    ).toBeInTheDocument();
  });

  it("displays the explanatory paragraph for the user", () => {
    renderNotFound();
    expect(
      screen.getByText(
        /A página que você está procurando não existe ou foi removida\./,
      ),
    ).toBeInTheDocument();
  });

  it("renders the back-to-home link", () => {
    renderNotFound();
    expect(
      screen.getByRole("link", { name: /Voltar ao início/i }),
    ).toBeInTheDocument();
  });
});

// ─── Navigation link ──────────────────────────────────────────────────────────

describe("NotFound - back-to-home link", () => {
  it("the link href points to the application root '/'", () => {
    renderNotFound();
    const link = screen.getByRole("link", { name: /Voltar ao início/i });
    expect(link).toHaveAttribute("href", "/");
  });

  it("link text matches the expected label exactly", () => {
    renderNotFound();
    const link = screen.getByRole("link", { name: /Voltar ao início/i });
    expect(link.textContent?.trim()).toBe("Voltar ao início");
  });
});

// ─── Accessibility ────────────────────────────────────────────────────────────

describe("NotFound - accessibility", () => {
  it("contains exactly one navigation link on the page", () => {
    renderNotFound();
    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(1);
  });

  it("heading is present and readable", () => {
    renderNotFound();
    // h1 tag used for the main message
    const heading = screen.getByRole("heading");
    expect(heading).toBeInTheDocument();
    expect(heading.textContent).toContain("não encontrada");
  });
});

// ─── Layout integrity ─────────────────────────────────────────────────────────

describe("NotFound - layout", () => {
  it("renders without throwing even when no specific route context is set", () => {
    expect(() => renderNotFound()).not.toThrow();
  });

  it("renders correctly when accessed from a deeply nested path", () => {
    renderNotFound("/dashboard/listings/999/edit/extra/path");
    expect(screen.getByText("404")).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /Voltar ao início/i });
    expect(link).toHaveAttribute("href", "/");
  });
});
