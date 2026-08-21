"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import { useApp } from "@/components/app-provider";
import { DatasetEvidencePanel } from "@/components/dataset-evidence-panel";
import { StaffResolutionDetails } from "@/components/staff-resolution-details";
import { createSubmissionGuard } from "@/lib/complaint-submission";
import { getDepartmentLabel } from "@/lib/department-labels";
import {
  StaffWorkflowError,
  loadStaffTicket,
  replyToTicket,
  requestStaffAction,
  transitionTicket,
  type StaffTicketDetail as Detail,
  type StaffWorkflowErrorCode,
} from "@/lib/staff-workflow";

function actionId(prefix: string) {
  return `${prefix}_${crypto.randomUUID()}`;
}

type StaffTicketMetadataProps = {
  ticketId: string;
  statusLabel: string;
  priorityLabel: string;
  createdAtLabel: string;
  updatedAtLabel: string;
  referenceLabel: string;
  statusTitle: string;
  priorityTitle: string;
  createdTitle: string;
  updatedTitle: string;
  departmentTitle: string;
  departmentLabel: string;
};

export function StaffTicketMetadata({
  ticketId,
  statusLabel,
  priorityLabel,
  createdAtLabel,
  updatedAtLabel,
  referenceLabel,
  statusTitle,
  priorityTitle,
  createdTitle,
  updatedTitle,
  departmentTitle,
  departmentLabel,
}: StaffTicketMetadataProps) {
  return (
    <dl className="ticket-metadata">
      <div><dt>{referenceLabel}</dt><dd className="ticket-reference">{ticketId}</dd></div>
      <div><dt>{statusTitle}</dt><dd>{statusLabel}</dd></div>
      <div><dt>{priorityTitle}</dt><dd>{priorityLabel}</dd></div>
      <div><dt>{createdTitle}</dt><dd>{createdAtLabel}</dd></div>
      <div><dt>{updatedTitle}</dt><dd>{updatedAtLabel}</dd></div>
      <div><dt>{departmentTitle}</dt><dd>{departmentLabel}</dd></div>
    </dl>
  );
}

export function StaffTicketDetail({ ticketId, getToken, onChanged }: { ticketId: string; getToken: () => Promise<string>; onChanged: () => Promise<void> }) {
  const { locale, t } = useApp();
  const [detail, setDetail] = useState<Detail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<StaffWorkflowErrorCode | null>(null);
  const [reply, setReply] = useState("");
  const [reason, setReason] = useState("");
  const [resolution, setResolution] = useState("");
  const [pending, setPending] = useState(false);
  const [activeTab, setActiveTab] = useState<"overview" | "messages" | "activity" | "model">("overview");
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const guard = useMemo(() => createSubmissionGuard(), []);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setDetail(await loadStaffTicket(await getToken(), ticketId));
    } catch (value) {
      setError(value instanceof StaffWorkflowError ? value.code : "backend");
    } finally {
      setLoading(false);
    }
  }, [getToken, ticketId]);

  useEffect(() => { queueMicrotask(() => void reload()); }, [reload]);
  const tabs = [
    { id: "overview", label: t("staffTabOverview") },
    { id: "messages", label: t("staffTabMessages") },
    { id: "activity", label: t("staffTabActivity") },
    { id: "model", label: t("staffTabModelData") },
  ] as const;

  function handleTabKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    const targetIndex = event.key === "ArrowRight"
      ? (index + 1) % tabs.length
      : event.key === "ArrowLeft"
        ? (index - 1 + tabs.length) % tabs.length
        : event.key === "Home"
          ? 0
          : event.key === "End"
            ? tabs.length - 1
            : -1;
    if (targetIndex < 0) return;
    event.preventDefault();
    setActiveTab(tabs[targetIndex].id);
    tabRefs.current[targetIndex]?.focus();
  }

  async function mutate(action: (token: string) => Promise<unknown>, clear: () => void) {
    await guard(async () => {
      setPending(true);
      setError(null);
      try {
        await action(await getToken());
        clear();
        await Promise.all([reload(), onChanged()]);
      } catch (value) {
        setError(value instanceof StaffWorkflowError ? value.code : "backend");
      } finally {
        setPending(false);
      }
    });
  }

  if (loading) return <div className="staff-detail-panel" role="status">{t("staffLoadingDetail")}</div>;
  if (error && !detail) return <div className="staff-detail-panel error-panel" role="alert">{t("staffBackendError")}</div>;
  if (!detail) return null;

  const date = new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" });
  const departmentLabel = getDepartmentLabel(detail.departmentId, locale) ?? t("evidenceUnavailable");
  const eventLabel = (type: string) => {
    const labels: Record<string, string> = {
      staff_reply: t("staffEventStaffReply"),
      customer_reply: t("staffEventCustomerReply"),
      status_transition: t("staffEventStatusTransition"),
      manager_override: t("staffEventManagerOverride"),
    };
    return labels[type] ?? t("staffEventUpdate");
  };
  const eventValue = (value: string | null) => {
    if (!value) return "—";
    const statusKeys = ["triaged", "in_progress", "awaiting_customer", "resolved"] as const;
    if (statusKeys.includes(value as typeof statusKeys[number])) return t(`status_${value}` as "status_triaged");
    return getDepartmentLabel(value, locale) ?? t("staffActivityValueUnavailable");
  };
  return (
    <article className="staff-detail-panel">
      <div className="staff-detail-heading">
        <h2>{t("staffDetailTitle")}</h2>
        <span className="staff-detail-context">{departmentLabel}</span>
      </div>
      <StaffTicketMetadata
        ticketId={detail.ticketId}
        statusLabel={t(`status_${detail.status}` as "status_triaged")}
        priorityLabel={t(`priority_${detail.priority}` as "priority_normal")}
        createdAtLabel={date.format(new Date(detail.createdAt))}
        updatedAtLabel={date.format(new Date(detail.updatedAt))}
        referenceLabel={t("staffReference")}
        statusTitle={t("staffStatus")}
        priorityTitle={t("staffPriority")}
        createdTitle={t("staffCreated")}
        updatedTitle={t("staffUpdated")}
        departmentTitle={t("staffDepartment")}
        departmentLabel={departmentLabel}
      />
      {error ? <div className="error-panel" role="alert">{t("staffActionError")}</div> : null}
      <div className="staff-tabs" role="tablist" aria-label={t("staffTabsLabel")}>
        {tabs.map((tab, index) => <button
          key={tab.id}
          ref={(element) => { tabRefs.current[index] = element; }}
          type="button"
          role="tab"
          id={`staff-tab-${tab.id}`}
          aria-controls={`staff-panel-${tab.id}`}
          aria-selected={activeTab === tab.id}
          tabIndex={activeTab === tab.id ? 0 : -1}
          onClick={() => setActiveTab(tab.id)}
          onKeyDown={(event) => handleTabKeyDown(event, index)}
        >{tab.label}</button>)}
      </div>
      {activeTab === "overview" ? <section id="staff-panel-overview" role="tabpanel" aria-labelledby="staff-tab-overview" tabIndex={0} className="staff-tab-panel">
        <h3>{t("staffOverviewHeading")}</h3>
        <p className="complaint-body">{detail.complaintText}</p>
        <StaffResolutionDetails
          resolutionSummary={detail.resolutionSummary}
          resolvedAt={detail.resolvedAt}
          resolutionLabel={t("staffResolution")}
          resolvedAtLabel={t("staffResolvedAt")}
          formatDate={(value) => date.format(value)}
        />
        <div className="staff-actions">
          {detail.status === "triaged" ? <button type="button" disabled={pending} onClick={() => void mutate((token) => transitionTicket(token, ticketId, "in_progress", actionId("transition")), () => undefined)}>{t("staffBegin")}</button> : null}
          {detail.status === "in_progress" ? <button type="button" disabled={pending} onClick={() => void mutate((token) => transitionTicket(token, ticketId, "awaiting_customer", actionId("transition")), () => undefined)}>{t("staffAwaitCustomer")}</button> : null}
          {detail.status === "awaiting_customer" ? <button type="button" disabled={pending} onClick={() => void mutate((token) => transitionTicket(token, ticketId, "in_progress", actionId("transition")), () => undefined)}>{t("staffResume")}</button> : null}
        </div>
        {detail.status === "in_progress" ? <form onSubmit={(event) => { event.preventDefault(); void mutate((token) => transitionTicket(token, ticketId, "resolved", actionId("resolve"), resolution), () => setResolution("")); }}><label htmlFor="staff-resolution">{t("staffResolution")}<textarea id="staff-resolution" required value={resolution} onChange={(event) => setResolution(event.target.value)} /></label><button disabled={pending}>{t("staffResolve")}</button></form> : null}
        <form onSubmit={(event) => event.preventDefault()}><label htmlFor="staff-request-reason">{t("staffRequestReason")}<textarea id="staff-request-reason" required value={reason} onChange={(event) => setReason(event.target.value)} /></label><div className="staff-actions"><button type="button" disabled={pending || !reason.trim()} onClick={() => void mutate((token) => requestStaffAction(token, ticketId, "request_reassignment", reason, actionId("request")), () => setReason(""))}>{t("staffRequestReassignment")}</button><button type="button" disabled={pending || !reason.trim()} onClick={() => void mutate((token) => requestStaffAction(token, ticketId, "request_escalation", reason, actionId("request")), () => setReason(""))}>{t("staffRequestEscalation")}</button></div></form>
      </section> : null}
      {activeTab === "messages" ? <section id="staff-panel-messages" role="tabpanel" aria-labelledby="staff-tab-messages" tabIndex={0} className="staff-tab-panel">
        <h3>{t("staffMessages")}</h3>
        {detail.messages.length ? detail.messages.map((message) => <div className="history-item" key={message.messageId}><strong>{message.authorRole === "customer" ? t("staffMessageCustomer") : t("staffMessageStaff")}</strong><p>{message.body}</p><time dateTime={message.createdAt}>{date.format(new Date(message.createdAt))}</time></div>) : <p>{t("staffNoMessages")}</p>}
        <form onSubmit={(event: FormEvent) => { event.preventDefault(); void mutate((token) => replyToTicket(token, ticketId, reply, actionId("reply")), () => setReply("")); }}><label htmlFor="staff-reply">{t("staffReply")}<textarea id="staff-reply" required value={reply} onChange={(event) => setReply(event.target.value)} /></label><button disabled={pending}>{t("staffSendReply")}</button></form>
      </section> : null}
      {activeTab === "activity" ? <section id="staff-panel-activity" role="tabpanel" aria-labelledby="staff-tab-activity" tabIndex={0} className="staff-tab-panel">
        <h3>{t("staffActivity")}</h3>
        {detail.events.length ? detail.events.map((event) => <div className="history-item" key={event.eventId}><strong>{eventLabel(event.type)}</strong><span>{event.fromValue || event.toValue ? `${eventValue(event.fromValue)} → ${eventValue(event.toValue)}` : t("staffActivityRecorded")}</span><time dateTime={event.createdAt}>{date.format(new Date(event.createdAt))}</time></div>) : <p>{t("staffNoEvents")}</p>}
      </section> : null}
      {activeTab === "model" ? <section id="staff-panel-model" role="tabpanel" aria-labelledby="staff-tab-model" tabIndex={0} className="staff-tab-panel">
        <DatasetEvidencePanel
          predictedDepartmentId={detail.predictedDepartmentId}
          predictionConfidence={detail.predictionConfidence}
          routingSource={detail.routingSource}
          assignedDepartmentId={detail.departmentId}
        />
      </section> : null}
    </article>
  );
}
