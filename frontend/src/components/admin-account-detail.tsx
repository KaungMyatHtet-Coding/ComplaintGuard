"use client";

import { createPortal } from "react-dom";
import { useEffect, useMemo, useRef } from "react";

import { useApp } from "@/components/app-provider";
import { getDepartmentLabel } from "@/lib/department-labels";
import type { AdminDirectoryResponse } from "@/lib/admin-directory";

type AdminDirectoryRow = AdminDirectoryResponse["rows"][number];

type AdminAccountDetailProps = {
  row: AdminDirectoryRow;
  openerRef: React.MutableRefObject<HTMLButtonElement | null>;
  fallbackRef: React.RefObject<HTMLElement | null>;
  canRestoreFocus: () => boolean;
  onClose: () => void;
};

function focusableElements(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>(
    "button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex=\"-1\"])",
  ));
}

export function AdminAccountDetail({ row, openerRef, fallbackRef, canRestoreFocus, onClose }: AdminAccountDetailProps) {
  const { locale, t } = useApp();
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const roleLabel = useMemo(() => {
    if (row.role === "customer") return t("adminCustomer");
    if (row.role === "staff") return t("adminStaff");
    if (row.role === "manager") return t("adminManager");
    return t("adminRoleAdmin");
  }, [row.role, t]);
  const explanation = useMemo(() => {
    if (row.role === "customer") return t("adminDetailCustomerExplanation");
    if (row.role === "staff") return t("adminDetailStaffExplanation");
    if (row.role === "manager") return t("adminDetailManagerExplanation");
    return t("adminDetailAdminExplanation");
  }, [row.role, t]);
  const title = row.displayName || t("adminDirectorySafeFallbackName");

  useEffect(() => {
    const dialog = dialogRef.current;
    const main = document.getElementById("dashboard-main") as HTMLElement | null;
    const header = document.querySelector(".app-header") as HTMLElement | null;
    const sidebar = document.querySelector(".dashboard-sidebar-host") as HTMLElement | null;
    const previousMainInert = main?.inert ?? false;
    const previousMainAriaHidden = main ? main.getAttribute("aria-hidden") : null;
    const previousHeaderInert = header?.inert ?? false;
    const previousHeaderAriaHidden = header ? header.getAttribute("aria-hidden") : null;
    const previousSidebarInert = sidebar?.inert ?? false;
    const previousSidebarAriaHidden = sidebar ? sidebar.getAttribute("aria-hidden") : null;
    const previousOverflow = document.body.style.overflow;
    if (!dialog) return;

    if (main) {
      main.inert = true;
      main.setAttribute("aria-hidden", "true");
    }
    if (header) {
      header.inert = true;
      header.setAttribute("aria-hidden", "true");
    }
    if (sidebar) {
      sidebar.inert = true;
      sidebar.setAttribute("aria-hidden", "true");
    }
    document.body.classList.add("admin-account-detail-open");
    document.body.style.overflow = "hidden";

    const focusCloseButton = () => closeButtonRef.current?.focus();
    const focusFallback = () => {
      const opener = openerRef.current;
      if (opener?.isConnected) opener.focus();
      else if (fallbackRef.current?.isConnected) fallbackRef.current.focus();
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = focusableElements(dialog);
      if (!focusable.length) {
        event.preventDefault();
        dialog.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    focusCloseButton();

    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.classList.remove("admin-account-detail-open");
      document.body.style.overflow = previousOverflow;
      if (main) {
        main.inert = previousMainInert;
        if (previousMainAriaHidden === null) main.removeAttribute("aria-hidden");
        else main.setAttribute("aria-hidden", previousMainAriaHidden);
      }
      if (header) {
        header.inert = previousHeaderInert;
        if (previousHeaderAriaHidden === null) header.removeAttribute("aria-hidden");
        else header.setAttribute("aria-hidden", previousHeaderAriaHidden);
      }
      if (sidebar) {
        sidebar.inert = previousSidebarInert;
        if (previousSidebarAriaHidden === null) sidebar.removeAttribute("aria-hidden");
        else sidebar.setAttribute("aria-hidden", previousSidebarAriaHidden);
      }
      if (canRestoreFocus()) focusFallback();
    };
  }, [canRestoreFocus, fallbackRef, onClose, openerRef]);

  const content = (
    <div className="admin-account-detail-overlay">
      <button className="admin-account-detail-backdrop" type="button" aria-label={t("adminAccountDetailClose")} onClick={onClose} />
      <div
        ref={dialogRef}
        className="admin-account-detail-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="admin-account-detail-title"
        tabIndex={-1}
      >
        <header className="admin-account-detail-header">
          <div>
            <p className="admin-section-eyebrow">{t("adminAccountDetailEyebrow")}</p>
            <h2 id="admin-account-detail-title">{title}</h2>
          </div>
          <button ref={closeButtonRef} className="admin-secondary-button" type="button" onClick={onClose} aria-label={t("adminAccountDetailClose")}>
            {t("adminAccountDetailClose")}
          </button>
        </header>
        <div className="admin-account-detail-body">
          <p className="admin-account-detail-lead">{t("adminAccountDetailLead")}</p>
          <dl className="admin-account-detail-fields">
            <div><dt>{t("adminDirectoryName")}</dt><dd>{title}</dd></div>
            <div><dt>{t("adminEmail")}</dt><dd className="admin-break-value">{row.email}</dd></div>
            <div><dt>{t("adminRole")}</dt><dd>{roleLabel}</dd></div>
            <div><dt>{t("adminDepartment")}</dt><dd>{row.departmentId ? getDepartmentLabel(row.departmentId, locale) : t("adminNotApplicable")}</dd></div>
            <div><dt>{t("adminDirectoryLanguage")}</dt><dd>{row.locale === "en" ? t("english") : t("myanmar")}</dd></div>
            <div><dt>{t("adminDirectoryStatus")}</dt><dd><span className={`admin-status-chip ${row.active ? "is-active" : "is-pending"}`}>{row.active ? t("adminDirectoryActive") : t("adminDirectoryPending")}</span></dd></div>
          </dl>
          <section className="admin-account-detail-explanation" aria-labelledby="admin-account-detail-explanation-title">
            <h3 id="admin-account-detail-explanation-title">{t("adminAccountDetailStatusTitle")}</h3>
            <p>{explanation}</p>
            {!row.active && (row.role === "staff" || row.role === "manager") ? <p>{t("adminDirectoryOwnerNotice")}</p> : null}
            <p>{t("adminDetailProfileStateNote")}</p>
          </section>
        </div>
      </div>
    </div>
  );

  return typeof document === "undefined" ? content : createPortal(content, document.body);
}
