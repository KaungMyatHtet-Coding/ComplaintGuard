"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { useApp } from "@/components/app-provider";
import {
  formatNotificationCount,
  getSafeNotificationTarget,
  getUnreadNotificationCount,
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  NotificationError,
  type NotificationItem,
} from "@/lib/notifications";
import type { MessageKey } from "@/lib/i18n";

type NotificationFilter = "all" | "unread";

function mergeNotifications(previous: NotificationItem[], next: NotificationItem[]) {
  const merged = new Map<string, NotificationItem>();
  [...previous, ...next].forEach((item) => merged.set(item.notificationRef, item));
  return Array.from(merged.values());
}

function errorMessage(error: unknown, t: (key: MessageKey) => string): string {
  if (error instanceof NotificationError && error.code === "auth") {
    return t("authError");
  }
  return t("notificationError");
}

function notificationText(t: (key: MessageKey) => string, key: string): string {
  return t(key as MessageKey);
}

export function NotificationCenter() {
  const { profile, locale, signOut, t } = useApp();
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState<NotificationFilter>("all");
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [unreadCount, setUnreadCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [reading, setReading] = useState<string | null>(null);
  const bellRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const requestRef = useRef(0);
  const countRequestRef = useRef(0);
  const controllersRef = useRef<Set<AbortController>>(new Set());
  const listControllerRef = useRef<AbortController | null>(null);
  const inFlightRef = useRef(false);
  const openRef = useRef(open);
  const filterRef = useRef(filter);
  const signOutStartedRef = useRef(false);
  const wasOpenRef = useRef(false);
  const refreshInFlightRef = useRef(false);

  useEffect(() => {
    openRef.current = open;
    filterRef.current = filter;
  }, [filter, open]);

  const refreshUnread = useCallback(async () => {
    const requestId = ++countRequestRef.current;
    const controller = new AbortController();
    controllersRef.current.add(controller);
    try {
      const count = await getUnreadNotificationCount(fetch, controller.signal);
      if (requestId === countRequestRef.current) setUnreadCount(count);
    } catch (caught) {
      if (requestId !== countRequestRef.current) return;
      if (caught instanceof NotificationError && caught.code === "auth" && !signOutStartedRef.current) {
        signOutStartedRef.current = true;
        await signOut();
      }
    } finally {
      controllersRef.current.delete(controller);
    }
  }, [signOut]);

  const loadPage = useCallback(async (reset: boolean, requestedFilter: NotificationFilter) => {
    if (inFlightRef.current) return;
    inFlightRef.current = true;
    const requestId = ++requestRef.current;
    const controller = new AbortController();
    controllersRef.current.add(controller);
    listControllerRef.current = controller;
    if (reset) setLoading(true);
    else setLoadingMore(true);
    setError(null);
    try {
      const response = await listNotifications({
        unreadOnly: requestedFilter === "unread",
        cursor: reset ? null : nextCursor,
        signal: controller.signal,
      });
      if (requestId !== requestRef.current) return;
      setNotifications((previous) => reset ? response.notifications : mergeNotifications(previous, response.notifications));
      const previousCursor = reset ? null : nextCursor;
      setNextCursor(response.nextCursor === previousCursor ? null : response.nextCursor);
    } catch (caught) {
      if (requestId !== requestRef.current) return;
      if (caught instanceof NotificationError && caught.code === "aborted") return;
      setError(errorMessage(caught, t));
      if (caught instanceof NotificationError && caught.code === "auth" && !signOutStartedRef.current) {
        signOutStartedRef.current = true;
        await signOut();
      }
    } finally {
      controllersRef.current.delete(controller);
      if (listControllerRef.current === controller) listControllerRef.current = null;
      inFlightRef.current = false;
      if (requestId === requestRef.current) {
        setLoading(false);
        setLoadingMore(false);
      }
    }
  }, [nextCursor, signOut, t]);

  const refresh = useCallback(async () => {
    if (refreshInFlightRef.current) return;
    refreshInFlightRef.current = true;
    try {
      await Promise.all([
        refreshUnread(),
        openRef.current ? loadPage(true, filterRef.current) : Promise.resolve(),
      ]);
      setFeedback(t("notificationUpdated"));
    } finally {
      refreshInFlightRef.current = false;
    }
  }, [loadPage, refreshUnread, t]);

  useEffect(() => {
    if (!profile) return;
    signOutStartedRef.current = false;
    const controllers = controllersRef.current;
    queueMicrotask(() => void refreshUnread());
    const refreshWhenVisible = () => {
      if (document.visibilityState === "visible") void refresh();
    };
    const refreshOnFocus = () => {
      if (document.visibilityState === "visible") void refresh();
    };
    const interval = window.setInterval(() => {
      if (document.visibilityState === "visible") void refresh();
    }, 60_000);
    document.addEventListener("visibilitychange", refreshWhenVisible);
    window.addEventListener("focus", refreshOnFocus);
    return () => {
      requestRef.current += 1;
      countRequestRef.current += 1;
      controllers.forEach((controller) => controller.abort());
      controllers.clear();
      inFlightRef.current = false;
      window.clearInterval(interval);
      document.removeEventListener("visibilitychange", refreshWhenVisible);
      window.removeEventListener("focus", refreshOnFocus);
    };
  }, [profile, refresh, refreshUnread]);

  useEffect(() => {
    if (!open) {
      if (wasOpenRef.current) bellRef.current?.focus();
      return;
    }
    wasOpenRef.current = true;
    requestAnimationFrame(() => {
      panelRef.current?.querySelector<HTMLElement>("button, [href], [tabindex='0']")?.focus();
    });
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open]);

  if (!profile) return null;

  const toggleOpen = () => {
    setOpen((current) => {
      const next = !current;
      if (next && notifications.length === 0 && !loading) void loadPage(true, filter);
      return next;
    });
  };

  const changeFilter = (nextFilter: NotificationFilter) => {
    if (nextFilter === filter) return;
    if (inFlightRef.current) {
      requestRef.current += 1;
      listControllerRef.current?.abort();
      listControllerRef.current = null;
      inFlightRef.current = false;
    }
    setFilter(nextFilter);
    setNotifications([]);
    setNextCursor(null);
    void loadPage(true, nextFilter);
  };

  const updateReadState = (notificationRef: string, readAt: string) => {
    setNotifications((items) => items.map((item) => item.notificationRef === notificationRef
      ? { ...item, readAt, unread: false }
      : item));
    setUnreadCount((count) => Math.max(0, count - 1));
  };

  const markRead = async (item: NotificationItem) => {
    if (!item.unread || reading) return true;
    setReading(item.notificationRef);
    const controller = new AbortController();
    controllersRef.current.add(controller);
    try {
      const readAt = await markNotificationRead(item.notificationRef, fetch, controller.signal);
      updateReadState(item.notificationRef, readAt);
      setFeedback(t("notificationMarkedRead"));
      return true;
    } catch (caught) {
      if (caught instanceof NotificationError && caught.code === "aborted") return false;
      setError(errorMessage(caught, t));
      if (caught instanceof NotificationError && caught.code === "auth" && !signOutStartedRef.current) {
        signOutStartedRef.current = true;
        await signOut();
      }
      return false;
    } finally {
      controllersRef.current.delete(controller);
      setReading(null);
    }
  };

  const openNotification = async (item: NotificationItem) => {
    const target = getSafeNotificationTarget(item);
    if (!target) {
      setFeedback(t("notificationNavigationUnavailable"));
      return;
    }
    if (!(await markRead(item))) return;
    setOpen(false);
    window.location.assign(target);
  };

  const markAllRead = async () => {
    if (unreadCount === 0 || reading) return;
    setReading("all");
    const controller = new AbortController();
    controllersRef.current.add(controller);
    try {
      const updatedCount = await markAllNotificationsRead(fetch, controller.signal);
      await refreshUnread();
      if (updatedCount > 0 && openRef.current) await loadPage(true, filterRef.current);
      setFeedback(t("notificationAllMarkedRead"));
    } catch (caught) {
      if (caught instanceof NotificationError && caught.code === "aborted") return;
      setError(errorMessage(caught, t));
      if (caught instanceof NotificationError && caught.code === "auth" && !signOutStartedRef.current) {
        signOutStartedRef.current = true;
        await signOut();
      }
    } finally {
      controllersRef.current.delete(controller);
      setReading(null);
    }
  };

  return (
    <div className="notification-center">
      <button
        ref={bellRef}
        type="button"
        className="notification-bell"
        aria-label={unreadCount > 0 ? `${t("notificationBell")}: ${formatNotificationCount(unreadCount)}` : t("notificationBell")}
        aria-expanded={open}
        aria-controls="notification-center-panel"
        onClick={toggleOpen}
      >
        <span aria-hidden="true" className="notification-bell-icon">♢</span>
        <span className="notification-bell-label">{t("notificationBell")}</span>
        {unreadCount > 0 ? <span className="notification-badge" aria-label={t("notificationUnreadCount").replace("{{count}}", formatNotificationCount(unreadCount))}>{formatNotificationCount(unreadCount)}</span> : null}
      </button>
      {open ? (
        <div className="notification-panel" id="notification-center-panel" ref={panelRef} role="dialog" aria-modal="false" aria-labelledby="notification-center-title">
          <div className="notification-panel-header">
            <div>
              <h2 id="notification-center-title">{t("notificationCenterTitle")}</h2>
              <p>{t("notificationClosedDelivery")}</p>
            </div>
            <button type="button" className="notification-close" onClick={() => setOpen(false)} aria-label={t("notificationClose")}>×</button>
          </div>
          <div className="notification-toolbar">
            <div className="notification-filters" role="group" aria-label={t("notificationCenterTitle")}>
              <button type="button" className={filter === "all" ? "is-active" : ""} aria-pressed={filter === "all"} onClick={() => changeFilter("all")}>{t("notificationAll")}</button>
              <button type="button" className={filter === "unread" ? "is-active" : ""} aria-pressed={filter === "unread"} onClick={() => changeFilter("unread")}>{t("notificationUnread")}</button>
            </div>
            <div className="notification-actions">
              <button type="button" onClick={() => void refresh()} disabled={loading || loadingMore}>{t("notificationRefresh")}</button>
              <button type="button" onClick={() => void markAllRead()} disabled={unreadCount === 0 || reading !== null}>{t("notificationMarkAllRead")}</button>
            </div>
          </div>
          {feedback ? <p className="notification-feedback" role="status">{feedback}</p> : null}
          {error ? <div className="notification-error" role="alert"><span>{error}</span><button type="button" onClick={() => void refresh()}>{t("notificationRetry")}</button></div> : null}
          {loading ? (
            <div className="notification-skeleton-list" aria-label={t("notificationLoading")} aria-busy="true">
              <span /><span /><span />
            </div>
          ) : notifications.length === 0 ? (
            <p className="notification-empty">{filter === "unread" ? t("notificationEmptyUnread") : profile.role === "customer" ? t("notificationEmpty") : t("notificationEmptyOtherRole")}</p>
          ) : (
            <div className="notification-list" aria-live="polite">
              {notifications.map((item) => (
                <article key={item.notificationRef} className={`notification-row${item.unread ? " is-unread" : ""}`}>
                  <button type="button" className="notification-row-main" onClick={() => void openNotification(item)} aria-label={`${notificationText(t, item.titleKey)}: ${notificationText(t, item.bodyKey)}`}>
                    <span className="notification-row-heading"><strong>{notificationText(t, item.titleKey)}</strong>{item.unread ? <span className="notification-unread-dot" aria-label={t("notificationUnread")} /> : null}</span>
                    <span className="notification-row-body">{notificationText(t, item.bodyKey)}</span>
                    <time dateTime={item.createdAt}>{new Date(item.createdAt).toLocaleString(locale === "my" ? "my-MM" : "en-US")}</time>
                  </button>
                  {item.unread ? <button type="button" className="notification-mark-read" onClick={() => void markRead(item)} disabled={reading !== null} aria-label={t("notificationMarkRead")}>{t("notificationMarkRead")}</button> : null}
                </article>
              ))}
            </div>
          )}
          {nextCursor ? <button type="button" className="notification-load-more" onClick={() => void loadPage(false, filter)} disabled={loading || loadingMore}>{loadingMore ? t("notificationLoading") : t("notificationLoadMore")}</button> : null}
        </div>
      ) : null}
      <div className="sr-only" role="status" aria-live="polite">{unreadCount > 0 ? t("notificationUnreadCount").replace("{{count}}", formatNotificationCount(unreadCount)) : ""}</div>
    </div>
  );
}
