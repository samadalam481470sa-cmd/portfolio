import type { Project, ProjectStatus, ServiceType } from "./types";

export const serviceOptions: ServiceType[] = [
  "Standard curb",
  "Cut curb",
  "Washout",
  "Retaining wall",
  "Sidewalk tie-in",
  "ADA ramp",
  "Demo and haul-off",
  "Other"
];

export const statusLabels: Record<ProjectStatus, string> = {
  "not-started": "Not started",
  started: "Started",
  finished: "Finished",
  complete: "Complete"
};

export const statusColumns: ProjectStatus[] = ["not-started", "started", "finished", "complete"];

export const sampleProjects: Project[] = [
  {
    id: "project-elmwood-curbs",
    name: "Elmwood Retail Frontage Curbs",
    contractor: "Northline General Contractors",
    subcontractor: "Precision Curb Crew",
    location: "Elmwood Plaza - Lot B",
    service: "Standard curb",
    status: "started",
    priority: "rush",
    startDate: "2026-06-04",
    dueDate: "2026-06-11",
    contractAmount: 18500,
    paidAmount: 6500,
    paymentStatus: "partial",
    notes: "Pour east drive aisle first. GC needs daily photo updates before 3 PM.",
    siteContact: "Maria Lopez - 555-0148",
    crewSize: 4,
    quantity: "1,820 LF curb and gutter",
    invoiceNumber: "INV-1048",
    tasks: [
      {
        id: "task-elmwood-layout",
        title: "Confirm final layout and control points",
        owner: "Contractor",
        dueDate: "2026-06-04",
        complete: true
      },
      {
        id: "task-elmwood-washout",
        title: "Set washout pit and send photo",
        owner: "Subcontractor",
        dueDate: "2026-06-04",
        complete: false
      },
      {
        id: "task-elmwood-pour",
        title: "Pour east drive aisle curb section",
        owner: "Subcontractor",
        dueDate: "2026-06-07",
        complete: false
      }
    ],
    documents: [
      {
        id: "document-elmwood-plan",
        name: "Elmwood approved curb layout.pdf",
        type: "application/pdf",
        size: 184320,
        dataUrl: "data:text/plain;charset=utf-8,Demo%20document%20placeholder%20for%20Elmwood%20approved%20curb%20layout.",
        uploadedBy: "Contractor",
        uploadedAt: "2026-06-02T15:00:00.000Z"
      }
    ],
    messages: [
      {
        id: "message-elmwood-1",
        sender: "Contractor",
        body: "Layout is approved. Please confirm crew size and washout plan before mobilizing.",
        createdAt: "2026-06-02T14:30:00.000Z"
      },
      {
        id: "message-elmwood-2",
        sender: "Subcontractor",
        body: "Four-person crew scheduled. Washout pit will be set on the west end by noon.",
        createdAt: "2026-06-02T16:10:00.000Z"
      }
    ],
    createdAt: "2026-06-01T12:00:00.000Z",
    updatedAt: "2026-06-02T16:10:00.000Z"
  },
  {
    id: "project-maple-cut-curbs",
    name: "Maple Street Cut Curb Package",
    contractor: "Canyon Siteworks",
    subcontractor: "Precision Curb Crew",
    location: "Maple Street subdivision entrances",
    service: "Cut curb",
    status: "not-started",
    priority: "waiting-on-info",
    startDate: "2026-06-13",
    dueDate: "2026-06-17",
    contractAmount: 9200,
    paidAmount: 0,
    paymentStatus: "unpaid",
    notes: "Waiting on revised traffic control plan and city inspector window.",
    siteContact: "Dave Morgan - 555-0182",
    crewSize: 3,
    quantity: "8 driveway cut-ins",
    invoiceNumber: "Draft",
    tasks: [
      {
        id: "task-maple-traffic",
        title: "Upload traffic control plan",
        owner: "Contractor",
        dueDate: "2026-06-10",
        complete: false
      },
      {
        id: "task-maple-sawcut",
        title: "Confirm sawcut crew and equipment",
        owner: "Subcontractor",
        dueDate: "2026-06-12",
        complete: false
      }
    ],
    documents: [
      {
        id: "document-maple-traffic",
        name: "Traffic control request.txt",
        type: "text/plain",
        size: 7200,
        dataUrl: "data:text/plain;charset=utf-8,Waiting%20on%20revised%20traffic%20control%20plan%20and%20city%20inspection%20window.",
        uploadedBy: "Contractor",
        uploadedAt: "2026-06-03T10:05:00.000Z"
      }
    ],
    messages: [
      {
        id: "message-maple-1",
        sender: "System",
        body: "Project created and marked waiting on information.",
        createdAt: "2026-06-03T09:45:00.000Z"
      }
    ],
    createdAt: "2026-06-03T09:45:00.000Z",
    updatedAt: "2026-06-03T09:45:00.000Z"
  },
  {
    id: "project-oak-retaining-wall",
    name: "Oak Basin Retaining Wall Repair",
    contractor: "Summit Builders",
    subcontractor: "Rock Solid Walls",
    location: "Oak Basin detention pond",
    service: "Retaining wall",
    status: "finished",
    priority: "normal",
    startDate: "2026-05-24",
    dueDate: "2026-05-31",
    completedDate: "2026-05-30",
    contractAmount: 27400,
    paidAmount: 12000,
    paymentStatus: "overdue",
    notes: "Substantial completion photos uploaded. Final pay app pending GC approval.",
    siteContact: "Andre Smith - 555-0111",
    crewSize: 5,
    quantity: "84 LF block wall repair",
    invoiceNumber: "INV-1032",
    tasks: [
      {
        id: "task-oak-punch",
        title: "Review punch list photos",
        owner: "Contractor",
        dueDate: "2026-06-02",
        complete: false
      },
      {
        id: "task-oak-invoice",
        title: "Send final pay application",
        owner: "Subcontractor",
        dueDate: "2026-06-01",
        complete: true
      },
      {
        id: "task-oak-release",
        title: "Release remaining payment",
        owner: "Contractor",
        dueDate: "2026-06-03",
        complete: false
      }
    ],
    documents: [
      {
        id: "document-oak-payapp",
        name: "Oak Basin final pay application.txt",
        type: "text/plain",
        size: 11300,
        dataUrl: "data:text/plain;charset=utf-8,Final%20pay%20application%20placeholder%20for%20Oak%20Basin%20Retaining%20Wall%20Repair.",
        uploadedBy: "Subcontractor",
        uploadedAt: "2026-05-30T19:08:00.000Z"
      }
    ],
    messages: [
      {
        id: "message-oak-1",
        sender: "Subcontractor",
        body: "Wall repair is finished. Please review the final invoice and release retainage.",
        createdAt: "2026-05-30T19:05:00.000Z"
      }
    ],
    createdAt: "2026-05-20T15:20:00.000Z",
    updatedAt: "2026-05-30T19:05:00.000Z"
  },
  {
    id: "project-harbor-washout",
    name: "Harbor Warehouse Washout Stations",
    contractor: "Blue Harbor Construction",
    subcontractor: "Precision Curb Crew",
    location: "Harbor Warehouse - Phase 2",
    service: "Washout",
    status: "complete",
    priority: "normal",
    startDate: "2026-05-10",
    dueDate: "2026-05-15",
    completedDate: "2026-05-14",
    contractAmount: 6100,
    paidAmount: 6100,
    paymentStatus: "paid",
    notes: "Paid in full. Keep record for May billing closeout.",
    siteContact: "Kenny Price - 555-0164",
    crewSize: 2,
    quantity: "3 washout stations",
    invoiceNumber: "INV-1017",
    tasks: [
      {
        id: "task-harbor-clean",
        title: "Remove washout station liners",
        owner: "Subcontractor",
        dueDate: "2026-05-15",
        complete: true
      },
      {
        id: "task-harbor-record",
        title: "Archive paid invoice record",
        owner: "Contractor",
        dueDate: "2026-05-18",
        complete: true
      }
    ],
    documents: [
      {
        id: "document-harbor-paid",
        name: "Paid invoice receipt.txt",
        type: "text/plain",
        size: 5400,
        dataUrl: "data:text/plain;charset=utf-8,Payment%20receipt%20placeholder%20for%20Harbor%20Warehouse%20Washout%20Stations.",
        uploadedBy: "Contractor",
        uploadedAt: "2026-05-18T13:14:00.000Z"
      }
    ],
    messages: [
      {
        id: "message-harbor-1",
        sender: "Contractor",
        body: "Payment has cleared. Marking the washout station scope complete.",
        createdAt: "2026-05-18T13:12:00.000Z"
      }
    ],
    createdAt: "2026-05-08T10:00:00.000Z",
    updatedAt: "2026-05-18T13:12:00.000Z"
  }
];
