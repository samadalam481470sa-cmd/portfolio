export type ServiceType =
  | "Standard curb"
  | "Cut curb"
  | "Washout"
  | "Retaining wall"
  | "Sidewalk tie-in"
  | "ADA ramp"
  | "Demo and haul-off"
  | "Other";

export type ProjectStatus = "not-started" | "started" | "finished" | "complete";

export type PaymentStatus = "unpaid" | "partial" | "paid" | "overdue";

export type Priority = "normal" | "rush" | "waiting-on-info";

export type MessageSender = "Contractor" | "Subcontractor" | "System";

export type TaskOwner = "Contractor" | "Subcontractor";

export interface ProjectMessage {
  id: string;
  sender: MessageSender;
  body: string;
  createdAt: string;
}

export interface ProjectTask {
  id: string;
  title: string;
  owner: TaskOwner;
  dueDate: string;
  complete: boolean;
}

export interface ProjectDocument {
  id: string;
  name: string;
  type: string;
  size: number;
  dataUrl: string;
  uploadedBy: MessageSender;
  uploadedAt: string;
}

export interface Project {
  id: string;
  name: string;
  contractor: string;
  subcontractor: string;
  location: string;
  service: ServiceType;
  status: ProjectStatus;
  priority: Priority;
  startDate: string;
  dueDate: string;
  completedDate?: string;
  contractAmount: number;
  paidAmount: number;
  paymentStatus: PaymentStatus;
  notes: string;
  siteContact: string;
  crewSize: number;
  quantity: string;
  invoiceNumber: string;
  tasks: ProjectTask[];
  documents: ProjectDocument[];
  messages: ProjectMessage[];
  createdAt: string;
  updatedAt: string;
}

export interface ProjectStats {
  totalProjects: number;
  notStarted: number;
  started: number;
  finished: number;
  complete: number;
  contractTotal: number;
  paidTotal: number;
  openBalance: number;
}
