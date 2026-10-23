import type { PaymentStatus, Project, ProjectStats } from "./types";

export function formatCurrency(amount: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0
  }).format(amount);
}

export function getOpenBalance(project: Pick<Project, "contractAmount" | "paidAmount">): number {
  return Math.max(project.contractAmount - project.paidAmount, 0);
}

export function inferPaymentStatus(
  contractAmount: number,
  paidAmount: number,
  dueDate?: string,
  today = new Date()
): PaymentStatus {
  if (contractAmount <= 0) {
    return paidAmount > 0 ? "paid" : "unpaid";
  }

  if (paidAmount >= contractAmount) {
    return "paid";
  }

  const balanceDue = contractAmount - paidAmount;
  const dueTimestamp = dueDate ? new Date(`${dueDate}T23:59:59`).getTime() : Number.NaN;

  if (balanceDue > 0 && Number.isFinite(dueTimestamp) && dueTimestamp < today.getTime()) {
    return "overdue";
  }

  return paidAmount > 0 ? "partial" : "unpaid";
}

export function getProjectStats(projects: Project[]): ProjectStats {
  return projects.reduce<ProjectStats>(
    (stats, project) => ({
      totalProjects: stats.totalProjects + 1,
      notStarted: stats.notStarted + (project.status === "not-started" ? 1 : 0),
      started: stats.started + (project.status === "started" ? 1 : 0),
      finished: stats.finished + (project.status === "finished" ? 1 : 0),
      complete: stats.complete + (project.status === "complete" ? 1 : 0),
      contractTotal: stats.contractTotal + project.contractAmount,
      paidTotal: stats.paidTotal + project.paidAmount,
      openBalance: stats.openBalance + getOpenBalance(project)
    }),
    {
      totalProjects: 0,
      notStarted: 0,
      started: 0,
      finished: 0,
      complete: 0,
      contractTotal: 0,
      paidTotal: 0,
      openBalance: 0
    }
  );
}

export function makeId(prefix: string): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return `${prefix}-${crypto.randomUUID()}`;
  }

  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}
