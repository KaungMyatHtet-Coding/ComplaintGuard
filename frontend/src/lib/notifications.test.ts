import { beforeEach, describe, expect, it, vi } from "vitest";

const { getFirebaseServices } = vi.hoisted(() => ({ getFirebaseServices: vi.fn() }));
vi.mock("@/lib/firebase", () => ({ getFirebaseServices }));
vi.mock("@/lib/runtime-environment", () => ({ resolveLocalMlApiBaseUrl: () => "http://127.0.0.1:8000" }));

import {
  formatNotificationCount,
  getSafeNotificationTarget,
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  NotificationError,
  notificationTypes,
  parseNotificationItem,
} from "./notifications";

const baseItem = {
  notificationRef: "a".repeat(64),
  type: "complaint_received",
  severity: "info",
  category: "complaint",
  relatedTicketRef: "ticket_public_1",
  titleKey: "notifications.complaint_received.title",
  bodyKey: "notifications.complaint_received.body",
  params: { ticketRef: "ticket_public_1" },
  navigationTarget: "customer_ticket",
  createdAt: "2026-08-22T10:00:00Z",
  readAt: null,
  unread: true,
} as const;

beforeEach(() => {
  getFirebaseServices.mockReturnValue({
    auth: { currentUser: { getIdToken: vi.fn().mockResolvedValue("fresh-token") } },
  });
});

describe("notification API contract", () => {
  it("uses fresh tokens, the backend page limit, and opaque cursors", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ notifications: [baseItem], nextCursor: "opaque-cursor" }), { status: 200 }));
    await expect(listNotifications({ cursor: "opaque-cursor", fetcher })).resolves.toMatchObject({ nextCursor: "opaque-cursor" });
    const [url, init] = fetcher.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://127.0.0.1:8000/notifications?pageSize=50&cursor=opaque-cursor");
    expect(init.headers).toEqual({ Authorization: "Bearer fresh-token" });
    expect(getFirebaseServices().auth.currentUser.getIdToken).toHaveBeenCalledWith(true);
  });

  it("accepts every approved type only through its matching localized keys", () => {
    for (const type of notificationTypes) {
      const item = {
        ...baseItem,
        type,
        titleKey: `notifications.${type}.title`,
        bodyKey: `notifications.${type}.body`,
        params: {},
        navigationTarget: "notifications",
        relatedTicketRef: null,
      };
      expect(() => parseNotificationItem(item)).not.toThrow();
    }
  });

  it("rejects private or unknown response fields", () => {
    expect(() => parseNotificationItem({ ...baseItem, recipientUid: "private" })).toThrowError(NotificationError);
    expect(() => parseNotificationItem({ ...baseItem, bodyKey: "notifications.complaint_received.title" })).toThrowError(NotificationError);
    expect(() => parseNotificationItem({ ...baseItem, params: { complaintText: "private narrative" } })).toThrowError(NotificationError);
    expect(() => parseNotificationItem({ ...baseItem, createdAt: "not-a-date" })).toThrowError(NotificationError);
    expect(() => parseNotificationItem({ ...baseItem, readAt: "not-a-date" })).toThrowError(NotificationError);
  });

  it("maps safe errors and protects read operations", async () => {
    for (const [status, code] of [[401, "auth"], [403, "permission"], [422, "validation"], [503, "unavailable"]] as const) {
      const fetcher = vi.fn().mockResolvedValue(new Response("{}", { status }));
      await expect(markAllNotificationsRead(fetcher)).rejects.toMatchObject({ code });
    }
    const fetcher = vi.fn();
    await expect(markNotificationRead("not-an-opaque-reference", fetcher)).rejects.toMatchObject({ code: "validation" });
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("treats an aborted request as non-user-facing cancellation", async () => {
    const fetcher = vi.fn().mockRejectedValue(new DOMException("cancelled", "AbortError"));
    await expect(listNotifications({ fetcher })).rejects.toMatchObject({ code: "aborted" });
  });

  it("uses only the safe customer target and rejects hostile targets", () => {
    expect(getSafeNotificationTarget(baseItem)).toBe("/dashboard?ticketRef=ticket_public_1");
    expect(getSafeNotificationTarget({ ...baseItem, navigationTarget: "notifications" })).toBeNull();
    expect(getSafeNotificationTarget({ ...baseItem, relatedTicketRef: "https://evil.test" })).toBeNull();
    expect(getSafeNotificationTarget({ ...baseItem, relatedTicketRef: "../private" })).toBeNull();
    expect(getSafeNotificationTarget({ ...baseItem, relatedTicketRef: "%2F%2Fevil.test" })).toBeNull();
    expect(getSafeNotificationTarget({ ...baseItem, navigationTarget: "https://evil.test" as never })).toBeNull();
    expect(getSafeNotificationTarget({ ...baseItem, navigationTarget: "customer_ticket", relatedTicketRef: null })).toBeNull();
  });

  it("caps visual counts and never changes the read-all API bound", async () => {
    expect(formatNotificationCount(0)).toBe("0");
    expect(formatNotificationCount(99)).toBe("99");
    expect(formatNotificationCount(1000)).toBe("99+");
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ updatedCount: 150 }), { status: 200 }));
    await expect(markAllNotificationsRead(fetcher)).resolves.toBe(150);
    expect((fetcher.mock.calls[0] as [string, RequestInit])[0]).toContain("/notifications/read-all");
  });
});
