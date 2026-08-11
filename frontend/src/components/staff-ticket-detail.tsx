"use client";

import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";

import { useApp } from "@/components/app-provider";
import { DatasetEvidencePanel } from "@/components/dataset-evidence-panel";
import { StaffResolutionDetails } from "@/components/staff-resolution-details";
import { createSubmissionGuard } from "@/lib/complaint-submission";
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
  referenceLabel: string;
  statusTitle: string;
  priorityTitle: string;
  createdTitle: string;
};

export function StaffTicketMetadata({
  ticketId,
  statusLabel,
  priorityLabel,
  createdAtLabel,
  referenceLabel,
  statusTitle,
  priorityTitle,
  createdTitle,
}: StaffTicketMetadataProps) {
  return (
    <dl className="ticket-metadata">
      <div><dt>{referenceLabel}</dt><dd className="ticket-reference">{ticketId}</dd></div>
      <div><dt>{statusTitle}</dt><dd>{statusLabel}</dd></div>
      <div><dt>{priorityTitle}</dt><dd>{priorityLabel}</dd></div>
      <div><dt>{createdTitle}</dt><dd>{createdAtLabel}</dd></div>
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
  return (
    <article className="staff-detail-panel">
      <h2>{t("staffDetailTitle")}</h2>
      <StaffTicketMetadata
        ticketId={detail.ticketId}
        statusLabel={t(`status_${detail.status}` as "status_triaged")}
        priorityLabel={t(`priority_${detail.priority}` as "priority_normal")}
        createdAtLabel={date.format(new Date(detail.createdAt))}
        referenceLabel={t("staffReference")}
        statusTitle={t("staffStatus")}
        priorityTitle={t("staffPriority")}
        createdTitle={t("staffCreated")}
      />
      <p className="complaint-body">{detail.complaintText}</p>
      <DatasetEvidencePanel
        predictedDepartmentId={detail.predictedDepartmentId}
        predictionConfidence={detail.predictionConfidence}
        routingSource={detail.routingSource}
        assignedDepartmentId={detail.departmentId}
      />
      <StaffResolutionDetails
        resolutionSummary={detail.resolutionSummary}
        resolvedAt={detail.resolvedAt}
        resolutionLabel={t("staffResolution")}
        resolvedAtLabel={t("staffResolvedAt")}
        formatDate={(value) => date.format(value)}
      />
      {error ? <div className="error-panel" role="alert">{t("staffActionError")}</div> : null}
      <div className="staff-actions">
        {detail.status === "triaged" ? <button disabled={pending} onClick={() => void mutate((token) => transitionTicket(token, ticketId, "in_progress", actionId("transition")), () => undefined)}>{t("staffBegin")}</button> : null}
        {detail.status === "in_progress" ? <button disabled={pending} onClick={() => void mutate((token) => transitionTicket(token, ticketId, "awaiting_customer", actionId("transition")), () => undefined)}>{t("staffAwaitCustomer")}</button> : null}
        {detail.status === "awaiting_customer" ? <button disabled={pending} onClick={() => void mutate((token) => transitionTicket(token, ticketId, "in_progress", actionId("transition")), () => undefined)}>{t("staffResume")}</button> : null}
      </div>
      {detail.status === "in_progress" ? <form onSubmit={(event) => { event.preventDefault(); void mutate((token) => transitionTicket(token, ticketId, "resolved", actionId("resolve"), resolution), () => setResolution("")); }}><label>{t("staffResolution")}<textarea required value={resolution} onChange={(event) => setResolution(event.target.value)} /></label><button disabled={pending}>{t("staffResolve")}</button></form> : null}
      <form onSubmit={(event: FormEvent) => { event.preventDefault(); void mutate((token) => replyToTicket(token, ticketId, reply, actionId("reply")), () => setReply("")); }}><label>{t("staffReply")}<textarea required value={reply} onChange={(event) => setReply(event.target.value)} /></label><button disabled={pending}>{t("staffSendReply")}</button></form>
      <form onSubmit={(event) => event.preventDefault()}><label>{t("staffRequestReason")}<textarea required value={reason} onChange={(event) => setReason(event.target.value)} /></label><div className="staff-actions"><button disabled={pending || !reason.trim()} onClick={() => void mutate((token) => requestStaffAction(token, ticketId, "request_reassignment", reason, actionId("request")), () => setReason(""))}>{t("staffRequestReassignment")}</button><button disabled={pending || !reason.trim()} onClick={() => void mutate((token) => requestStaffAction(token, ticketId, "request_escalation", reason, actionId("request")), () => setReason(""))}>{t("staffRequestEscalation")}</button></div></form>
      <section><h3>{t("staffMessages")}</h3>{detail.messages.length ? detail.messages.map((message) => <div className="history-item" key={message.messageId}><strong>{message.authorRole}</strong><p>{message.body}</p><time>{date.format(new Date(message.createdAt))}</time></div>) : <p>{t("staffNoMessages")}</p>}</section>
      <section><h3>{t("staffAudit")}</h3>{detail.events.length ? detail.events.map((event) => <div className="history-item" key={event.eventId}><strong>{event.type}</strong><span>{event.fromValue ?? "—"} → {event.toValue ?? "—"}</span><time>{date.format(new Date(event.createdAt))}</time></div>) : <p>{t("staffNoEvents")}</p>}</section>
    </article>
  );
}
