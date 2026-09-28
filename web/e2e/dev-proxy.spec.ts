import { expect, test } from "@playwright/test";

// Every spec mocks /api in the browser, and one that navigates before mocking sends its
// requests through the dev server's proxy. The proxy must lead nowhere, not to the crew that
// may be running on this machine on the server's default port.
test("a request no spec mocked goes nowhere, not to a server on this machine", async ({ request }) => {
  const response = await request.get("/api/health");
  expect(response.ok()).toBe(false);
});
