import { type ChangeEvent, type FormEvent, useEffect, useMemo, useState } from "react";
import { resetProjects, loadProjects, saveProjects } from "./storage";
import { serviceOptions, statusColumns, statusLabels } from "./sampleData";
import { formatCurrency, getOpenBalance, getProjectStats, inferPaymentStatus, makeId } from "./projectUtils";
import type { Priority, Project, ProjectDocument, ProjectMessage, ProjectStatus, ProjectTask, ServiceType, TaskOwner } from "./types";

type RoleMode = "contractor" | "subcontractor";

interface ProjectFormState {
  name: string;
  contractor: string;
  subcontractor: string;
  location: string;
  service: ServiceType;
  status: ProjectStatus;
  priority: Priority;
  startDate: string;
  dueDate: string;
  contractAmount: string;
  siteContact: string;
  crewSize: string;
  quantity: string;
  invoiceNumber: string;
  notes: string;
}

const emptyProjectForm: ProjectFormState = {
  name: "",
  contractor: "",
  subcontractor: "",
  location: "",
  service: "Standard curb",
  status: "not-started",
  priority: "normal",
  startDate: "",
  dueDate: "",
  contractAmount: "",
  siteContact: "",
  crewSize: "",
  quantity: "",
  invoiceNumber: "",
  notes: ""
};

const priorityLabels: Record<Priority, string> = {
  normal: "Normal",
  rush: "Rush",
  "waiting-on-info": "Waiting on info"
};

const roleCopy: Record<
  RoleMode,
  {
    label: string;
    eyebrow: string;
    headline: string;
    description: string;
    taskTitle: string;
    moneyTitle: string;
  }
> = {
  contractor: {
    label: "Contractor view",
    eyebrow: "Prime contractor controls",
    headline: "Approve work, track subs, and close out payments.",
    description:
      "This view highlights approvals, plan blockers, punch list items, invoices, and balances that the contractor needs to move.",
    taskTitle: "Contractor to-do list",
    moneyTitle: "Payment approvals"
  },
  subcontractor: {
    label: "Subcontractor view",
    eyebrow: "Crew and field controls",
    headline: "See what to build next and what needs to be sent back.",
    description:
      "This view focuses on crew tasks, washout setup, pour dates, field updates, completion photos, and invoices waiting on the contractor.",
    taskTitle: "Subcontractor field list",
    moneyTitle: "Invoices and balances"
  }
};

function parseMoney(value: string): number {
  const parsed = Number.parseFloat(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function parseWholeNumber(value: string): number {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) ? parsed : 0;
}

function formatDate(value?: string): string {
  if (!value) {
    return "Not set";
  }

  return new Date(`${value}T12:00:00`).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric"
  });
}

function formatDateTime(value: string): string {
  return new Date(value).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit"
  });
}

function todayIsoDate(): string {
  return new Date().toISOString().slice(0, 10);
}

function currentTaskOwner(roleMode: RoleMode): TaskOwner {
  return roleMode === "contractor" ? "Contractor" : "Subcontractor";
}

function getTasks(project: Project): ProjectTask[] {
  return project.tasks ?? [];
}

function getDocuments(project: Project): ProjectDocument[] {
  return project.documents ?? [];
}

function formatFileSize(size: number): string {
  if (size < 1024) {
    return `${size} B`;
  }

  if (size < 1024 * 1024) {
    return `${Math.round(size / 1024)} KB`;
  }

  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new window.FileReader();

    reader.addEventListener("load", () => {
      if (typeof reader.result === "string") {
        resolve(reader.result);
      } else {
        reject(new Error("Could not read file."));
      }
    });
    reader.addEventListener("error", () => reject(reader.error ?? new Error("Could not read file.")));
    reader.readAsDataURL(file);
  });
}

function getTaskProgress(project: Project): { complete: number; total: number; percent: number } {
  const tasks = getTasks(project);
  const complete = tasks.filter((task) => task.complete).length;
  const total = tasks.length;
  return { complete, total, percent: total === 0 ? 0 : Math.round((complete / total) * 100) };
}

function buildSystemMessage(body: string): ProjectMessage {
  return {
    id: makeId("message"),
    sender: "System",
    body,
    createdAt: new Date().toISOString()
  };
}

function App() {
  const [projects, setProjects] = useState<Project[]>(() => loadProjects());
  const [roleMode, setRoleMode] = useState<RoleMode>("contractor");
  const [projectForm, setProjectForm] = useState<ProjectFormState>(emptyProjectForm);
  const [formError, setFormError] = useState("");
  const [searchTerm, setSearchTerm] = useState("");
  const [serviceFilter, setServiceFilter] = useState<ServiceType | "all">("all");
  const [statusFilter, setStatusFilter] = useState<ProjectStatus | "all">("all");
  const [messageDrafts, setMessageDrafts] = useState<Record<string, string>>({});
  const [paymentDrafts, setPaymentDrafts] = useState<Record<string, string>>({});
  const [taskDrafts, setTaskDrafts] = useState<Record<string, string>>({});

  useEffect(() => {
    saveProjects(projects);
  }, [projects]);

  const stats = useMemo(() => getProjectStats(projects), [projects]);
  const roleOwner = currentTaskOwner(roleMode);
  const copy = roleCopy[roleMode];

  const roleTasks = useMemo(
    () =>
      projects
        .flatMap((project) =>
          getTasks(project)
            .filter((task) => task.owner === roleOwner && !task.complete)
            .map((task) => ({ project, task }))
        )
        .sort((a, b) => a.task.dueDate.localeCompare(b.task.dueDate)),
    [projects, roleOwner]
  );

  const paymentFocus = useMemo(
    () =>
      projects
        .filter((project) => getOpenBalance(project) > 0 && project.status !== "complete")
        .sort((a, b) => getOpenBalance(b) - getOpenBalance(a))
        .slice(0, 4),
    [projects]
  );

  const filteredProjects = useMemo(() => {
    const normalizedSearch = searchTerm.trim().toLowerCase();

    return projects.filter((project) => {
      const matchesSearch =
        normalizedSearch.length === 0 ||
        [
          project.name,
          project.contractor,
          project.subcontractor,
          project.location,
          project.notes,
          project.siteContact,
          project.quantity,
          project.invoiceNumber
        ]
          .join(" ")
          .toLowerCase()
          .includes(normalizedSearch);
      const matchesService = serviceFilter === "all" || project.service === serviceFilter;
      const matchesStatus = statusFilter === "all" || project.status === statusFilter;

      return matchesSearch && matchesService && matchesStatus;
    });
  }, [projects, searchTerm, serviceFilter, statusFilter]);

  const rollingProjects = useMemo(
    () => [...filteredProjects].sort((a, b) => a.dueDate.localeCompare(b.dueDate)),
    [filteredProjects]
  );

  function handleProjectFieldChange(
    event: ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>
  ) {
    const { name, value } = event.target;
    setProjectForm((current) => ({ ...current, [name]: value }));
  }

  function handleCreateProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!projectForm.name.trim() || !projectForm.contractor.trim() || !projectForm.subcontractor.trim()) {
      setFormError("Project name, contractor, and subcontractor are required.");
      return;
    }

    const timestamp = new Date().toISOString();
    const contractAmount = parseMoney(projectForm.contractAmount);
    const firstTaskTitle = projectForm.status === "not-started" ? "Confirm schedule and release to field" : "Send field update";
    const initialMessage = projectForm.notes.trim()
      ? [
          {
            id: makeId("message"),
            sender: roleMode === "contractor" ? "Contractor" : "Subcontractor",
            body: `Project notes: ${projectForm.notes.trim()}`,
            createdAt: timestamp
          } satisfies ProjectMessage
        ]
      : [buildSystemMessage("Project created and ready for coordination.")];

    const project: Project = {
      id: makeId("project"),
      name: projectForm.name.trim(),
      contractor: projectForm.contractor.trim(),
      subcontractor: projectForm.subcontractor.trim(),
      location: projectForm.location.trim() || "Location not set",
      service: projectForm.service,
      status: projectForm.status,
      priority: projectForm.priority,
      startDate: projectForm.startDate,
      dueDate: projectForm.dueDate,
      completedDate: projectForm.status === "finished" || projectForm.status === "complete" ? todayIsoDate() : undefined,
      contractAmount,
      paidAmount: 0,
      paymentStatus: inferPaymentStatus(contractAmount, 0, projectForm.dueDate),
      notes: projectForm.notes.trim(),
      siteContact: projectForm.siteContact.trim() || "No site contact added",
      crewSize: parseWholeNumber(projectForm.crewSize),
      quantity: projectForm.quantity.trim() || "Quantity not set",
      invoiceNumber: projectForm.invoiceNumber.trim() || "Draft",
      tasks: [
        {
          id: makeId("task"),
          title: firstTaskTitle,
          owner: roleOwner,
          dueDate: projectForm.startDate || projectForm.dueDate || todayIsoDate(),
          complete: false
        }
      ],
      documents: [],
      messages: initialMessage,
      createdAt: timestamp,
      updatedAt: timestamp
    };

    setProjects((current) => [project, ...current]);
    setProjectForm(emptyProjectForm);
    setFormError("");
  }

  function updateProjectStatus(projectId: string, status: ProjectStatus) {
    const timestamp = new Date().toISOString();
    setProjects((current) =>
      current.map((project) => {
        if (project.id !== projectId) {
          return project;
        }

        return {
          ...project,
          status,
          completedDate:
            status === "finished" || status === "complete" ? project.completedDate ?? todayIsoDate() : undefined,
          updatedAt: timestamp,
          messages: [buildSystemMessage(`Status changed to ${statusLabels[status]}.`), ...project.messages]
        };
      })
    );
  }

  function toggleTask(projectId: string, taskId: string) {
    const timestamp = new Date().toISOString();
    setProjects((current) =>
      current.map((project) =>
        project.id === projectId
          ? {
              ...project,
              tasks: getTasks(project).map((task) =>
                task.id === taskId ? { ...task, complete: !task.complete } : task
              ),
              updatedAt: timestamp
            }
          : project
      )
    );
  }

  function addTask(projectId: string) {
    const draft = (taskDrafts[projectId] ?? "").trim();

    if (!draft) {
      return;
    }

    const timestamp = new Date().toISOString();
    setProjects((current) =>
      current.map((project) =>
        project.id === projectId
          ? {
              ...project,
              tasks: [
                ...getTasks(project),
                {
                  id: makeId("task"),
                  title: draft,
                  owner: roleOwner,
                  dueDate: project.dueDate || todayIsoDate(),
                  complete: false
                }
              ],
              updatedAt: timestamp,
              messages: [buildSystemMessage(`${roleOwner} task added: ${draft}`), ...project.messages]
            }
          : project
      )
    );
    setTaskDrafts((current) => ({ ...current, [projectId]: "" }));
  }

  async function uploadDocuments(projectId: string, fileList: FileList | null) {
    const files = Array.from(fileList ?? []);

    if (files.length === 0) {
      return;
    }

    const timestamp = new Date().toISOString();
    const uploadedBy: ProjectDocument["uploadedBy"] = roleMode === "contractor" ? "Contractor" : "Subcontractor";
    const documents = await Promise.all(
      files.map(async (file) => ({
        id: makeId("document"),
        name: file.name,
        type: file.type || "application/octet-stream",
        size: file.size,
        dataUrl: await readFileAsDataUrl(file),
        uploadedBy,
        uploadedAt: timestamp
      }))
    );

    setProjects((current) =>
      current.map((project) =>
        project.id === projectId
          ? {
              ...project,
              documents: [...documents, ...getDocuments(project)],
              updatedAt: timestamp,
              messages: [
                buildSystemMessage(
                  `${uploadedBy} uploaded ${documents.length} document${documents.length === 1 ? "" : "s"}.`
                ),
                ...project.messages
              ]
            }
          : project
      )
    );
  }

  function removeDocument(projectId: string, documentId: string) {
    const timestamp = new Date().toISOString();
    setProjects((current) =>
      current.map((project) =>
        project.id === projectId
          ? {
              ...project,
              documents: getDocuments(project).filter((document) => document.id !== documentId),
              updatedAt: timestamp,
              messages: [buildSystemMessage("Document removed from project record."), ...project.messages]
            }
          : project
      )
    );
  }

  function recordPayment(projectId: string) {
    const amount = parseMoney(paymentDrafts[projectId] ?? "");

    if (amount <= 0) {
      return;
    }

    setProjects((current) =>
      current.map((project) => {
        if (project.id !== projectId) {
          return project;
        }

        const paidAmount = project.paidAmount + amount;
        const timestamp = new Date().toISOString();
        const paymentStatus = inferPaymentStatus(project.contractAmount, paidAmount, project.dueDate);
        const shouldCloseProject = paymentStatus === "paid" && project.status === "finished";

        return {
          ...project,
          paidAmount,
          paymentStatus,
          status: shouldCloseProject ? "complete" : project.status,
          completedDate: shouldCloseProject ? project.completedDate ?? todayIsoDate() : project.completedDate,
          updatedAt: timestamp,
          messages: [
            {
              id: makeId("message"),
              sender: "System",
              body: `Payment logged: ${formatCurrency(amount)}. Open balance is ${formatCurrency(
                Math.max(project.contractAmount - paidAmount, 0)
              )}.`,
              createdAt: timestamp
            },
            ...project.messages
          ]
        };
      })
    );
    setPaymentDrafts((current) => ({ ...current, [projectId]: "" }));
  }

  function addMessage(projectId: string) {
    const draft = (messageDrafts[projectId] ?? "").trim();

    if (!draft) {
      return;
    }

    const timestamp = new Date().toISOString();
    const message: ProjectMessage = {
      id: makeId("message"),
      sender: roleMode === "contractor" ? "Contractor" : "Subcontractor",
      body: draft,
      createdAt: timestamp
    };

    setProjects((current) =>
      current.map((project) =>
        project.id === projectId
          ? {
              ...project,
              updatedAt: timestamp,
              messages: [message, ...project.messages]
            }
          : project
      )
    );
    setMessageDrafts((current) => ({ ...current, [projectId]: "" }));
  }

  function handleResetDemoData() {
    setProjects(resetProjects());
    setSearchTerm("");
    setServiceFilter("all");
    setStatusFilter("all");
  }

  return (
    <main className="app-shell">
      <section className="hero">
        <div>
          <p className="eyebrow">Contractor and subcontractor command center</p>
          <h1>Curb Connect</h1>
          <p className="hero-copy">
            Track curb, washout, cut curb, retaining wall, and site concrete work from not started to paid
            complete. Keep project messages, field tasks, due dates, and payment records in one place.
          </p>
          <div className="hero-actions" aria-label="Choose app role">
            {(Object.keys(roleCopy) as RoleMode[]).map((role) => (
              <button
                className={roleMode === role ? "active" : ""}
                key={role}
                type="button"
                onClick={() => setRoleMode(role)}
              >
                {roleCopy[role].label}
              </button>
            ))}
          </div>
        </div>
        <aside className="hero-panel">
          <span>Open balance</span>
          <strong>{formatCurrency(stats.openBalance)}</strong>
          <small>{roleTasks.length} open {roleOwner.toLowerCase()} tasks need attention.</small>
        </aside>
      </section>

      <section className={`role-dashboard ${roleMode}`}>
        <article className="role-card">
          <p className="eyebrow">{copy.eyebrow}</p>
          <h2>{copy.headline}</h2>
          <p>{copy.description}</p>
          <div className="role-metrics">
            <span>{stats.started} active</span>
            <span>{stats.finished} ready to close</span>
            <span>{stats.notStarted} waiting to start</span>
          </div>
        </article>
        <article className="role-card action-card">
          <div className="section-heading tight">
            <p className="eyebrow">{copy.taskTitle}</p>
            <h3>Next things to do</h3>
          </div>
          <div className="quick-list">
            {roleTasks.slice(0, 5).map(({ project, task }) => (
              <button className="quick-task" key={`${project.id}-${task.id}`} type="button" onClick={() => toggleTask(project.id, task.id)}>
                <span>{task.title}</span>
                <small>{project.name} - due {formatDate(task.dueDate)}</small>
              </button>
            ))}
            {roleTasks.length === 0 ? <p className="empty-state compact">No open tasks for this view.</p> : null}
          </div>
        </article>
        <article className="role-card money-card">
          <div className="section-heading tight">
            <p className="eyebrow">{copy.moneyTitle}</p>
            <h3>Money to watch</h3>
          </div>
          <div className="quick-list">
            {paymentFocus.map((project) => (
              <div className="money-focus" key={project.id}>
                <span>{project.name}</span>
                <strong>{formatCurrency(getOpenBalance(project))}</strong>
              </div>
            ))}
          </div>
        </article>
      </section>

      <section className="stats-grid" aria-label="Project summary">
        <article>
          <span>Total projects</span>
          <strong>{stats.totalProjects}</strong>
          <small>{formatCurrency(stats.contractTotal)} under contract</small>
        </article>
        <article>
          <span>Not started</span>
          <strong>{stats.notStarted}</strong>
          <small>Waiting on schedule, scope, or approvals</small>
        </article>
        <article>
          <span>Started</span>
          <strong>{stats.started}</strong>
          <small>Crews are active or mobilized</small>
        </article>
        <article>
          <span>Finished</span>
          <strong>{stats.finished}</strong>
          <small>Ready for review, invoice, or closeout</small>
        </article>
        <article>
          <span>Paid complete</span>
          <strong>{stats.complete}</strong>
          <small>{formatCurrency(stats.paidTotal)} collected</small>
        </article>
      </section>

      <section className="card rolling-section">
        <div className="section-heading spread">
          <div>
            <p className="eyebrow">Rolling job list</p>
            <h2>Swipe sideways to see upcoming jobs</h2>
          </div>
          <small>{rollingProjects.length} jobs showing</small>
        </div>
        <div className="rolling-job-strip" aria-label="Horizontally scrolling job list">
          {rollingProjects.map((project) => {
            const progress = getTaskProgress(project);
            return (
              <article className="rolling-job" key={project.id}>
                <div className="rolling-topline">
                  <span className="scope-pill">{project.service}</span>
                  <span className={`priority-pill ${project.priority}`}>{priorityLabels[project.priority]}</span>
                </div>
                <h3>{project.name}</h3>
                <p>{project.location}</p>
                <dl>
                  <div>
                    <dt>Status</dt>
                    <dd>{statusLabels[project.status]}</dd>
                  </div>
                  <div>
                    <dt>Due</dt>
                    <dd>{formatDate(project.dueDate)}</dd>
                  </div>
                  <div>
                    <dt>Tasks</dt>
                    <dd>{progress.complete}/{progress.total}</dd>
                  </div>
                  <div>
                    <dt>Balance</dt>
                    <dd>{formatCurrency(getOpenBalance(project))}</dd>
                  </div>
                </dl>
                <div className="progress-track" aria-label={`${project.name} task progress`}>
                  <span style={{ width: `${progress.percent}%` }} />
                </div>
              </article>
            );
          })}
        </div>
      </section>

      <section className="workspace-grid">
        <form className="project-form card" onSubmit={handleCreateProject}>
          <div className="section-heading">
            <p className="eyebrow">New work order</p>
            <h2>Add a project</h2>
          </div>

          {formError ? <p className="form-error">{formError}</p> : null}

          <label>
            Project name
            <input
              name="name"
              value={projectForm.name}
              onChange={handleProjectFieldChange}
              placeholder="Example: Lot 12 cut curb package"
            />
          </label>

          <div className="two-column">
            <label>
              Contractor
              <input
                name="contractor"
                value={projectForm.contractor}
                onChange={handleProjectFieldChange}
                placeholder="General contractor"
              />
            </label>
            <label>
              Subcontractor
              <input
                name="subcontractor"
                value={projectForm.subcontractor}
                onChange={handleProjectFieldChange}
                placeholder="Concrete/curb crew"
              />
            </label>
          </div>

          <div className="two-column">
            <label>
              Location
              <input
                name="location"
                value={projectForm.location}
                onChange={handleProjectFieldChange}
                placeholder="Site, phase, or address"
              />
            </label>
            <label>
              Site contact
              <input
                name="siteContact"
                value={projectForm.siteContact}
                onChange={handleProjectFieldChange}
                placeholder="Name and phone"
              />
            </label>
          </div>

          <div className="two-column">
            <label>
              Scope option
              <select name="service" value={projectForm.service} onChange={handleProjectFieldChange}>
                {serviceOptions.map((service) => (
                  <option key={service} value={service}>
                    {service}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Status
              <select name="status" value={projectForm.status} onChange={handleProjectFieldChange}>
                {statusColumns.map((status) => (
                  <option key={status} value={status}>
                    {statusLabels[status]}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="three-column">
            <label>
              Priority
              <select name="priority" value={projectForm.priority} onChange={handleProjectFieldChange}>
                {(Object.keys(priorityLabels) as Priority[]).map((priority) => (
                  <option key={priority} value={priority}>
                    {priorityLabels[priority]}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Start
              <input name="startDate" type="date" value={projectForm.startDate} onChange={handleProjectFieldChange} />
            </label>
            <label>
              Due
              <input name="dueDate" type="date" value={projectForm.dueDate} onChange={handleProjectFieldChange} />
            </label>
          </div>

          <div className="three-column">
            <label>
              Contract amount
              <input
                name="contractAmount"
                type="number"
                min="0"
                step="100"
                value={projectForm.contractAmount}
                onChange={handleProjectFieldChange}
                placeholder="0"
              />
            </label>
            <label>
              Crew size
              <input
                name="crewSize"
                type="number"
                min="0"
                value={projectForm.crewSize}
                onChange={handleProjectFieldChange}
                placeholder="4"
              />
            </label>
            <label>
              Invoice number
              <input
                name="invoiceNumber"
                value={projectForm.invoiceNumber}
                onChange={handleProjectFieldChange}
                placeholder="INV-1050 or Draft"
              />
            </label>
          </div>

          <label>
            Quantity / footage
            <input
              name="quantity"
              value={projectForm.quantity}
              onChange={handleProjectFieldChange}
              placeholder="Example: 850 LF curb, 3 washouts, 2 ramps"
            />
          </label>

          <label>
            Scope notes or first message
            <textarea
              name="notes"
              value={projectForm.notes}
              onChange={handleProjectFieldChange}
              placeholder="Add washout needs, curb footage, forms, inspector notes, retainage, or payment terms."
              rows={4}
            />
          </label>

          <button className="primary-button" type="submit">
            Create project record
          </button>
        </form>

        <section className="card schedule-card">
          <div className="section-heading">
            <p className="eyebrow">Job tools</p>
            <h2>What else is inside</h2>
          </div>
          <div className="tool-list">
            <article>
              <strong>Field tasks</strong>
              <span>Add and check off owner-specific tasks for either side.</span>
            </article>
            <article>
              <strong>Payment records</strong>
              <span>Log partial payments and auto-close finished paid jobs.</span>
            </article>
            <article>
              <strong>Job details</strong>
              <span>Track footage, crew size, site contact, invoice number, and due dates.</span>
            </article>
            <article>
              <strong>Communication log</strong>
              <span>Keep contractor and subcontractor updates with time stamps.</span>
            </article>
          </div>
          <button className="secondary-button" type="button" onClick={handleResetDemoData}>
            Reset demo records
          </button>
        </section>
      </section>

      <section className="card filters-card">
        <div>
          <p className="eyebrow">Records</p>
          <h2>Find project communication, tasks, and payment history</h2>
        </div>
        <div className="filters">
          <input
            aria-label="Search projects"
            value={searchTerm}
            onChange={(event) => setSearchTerm(event.target.value)}
            placeholder="Search job, company, site, contact, invoice, or notes"
          />
          <select
            aria-label="Filter by service"
            value={serviceFilter}
            onChange={(event) => setServiceFilter(event.target.value as ServiceType | "all")}
          >
            <option value="all">All scope options</option>
            {serviceOptions.map((service) => (
              <option key={service} value={service}>
                {service}
              </option>
            ))}
          </select>
          <select
            aria-label="Filter by status"
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value as ProjectStatus | "all")}
          >
            <option value="all">All statuses</option>
            {statusColumns.map((status) => (
              <option key={status} value={status}>
                {statusLabels[status]}
              </option>
            ))}
          </select>
        </div>
      </section>

      <section className="project-directory" aria-label="Project records">
        {filteredProjects.map((project) => {
          const progress = getTaskProgress(project);
          return (
            <article className="wide-project-card" key={project.id}>
              <div className="wide-project-main">
                <div className="project-title-row">
                  <div>
                    <span className="scope-pill">{project.service}</span>
                    <h3>{project.name}</h3>
                    <p>{project.location}</p>
                  </div>
                  <div className="status-stack">
                    <span className={`payment-pill ${project.paymentStatus}`}>{project.paymentStatus}</span>
                    <span className={`priority-pill ${project.priority}`}>{priorityLabels[project.priority]}</span>
                  </div>
                </div>

                <div className="detail-grid">
                  <div>
                    <span>Contractor</span>
                    <strong>{project.contractor}</strong>
                  </div>
                  <div>
                    <span>Subcontractor</span>
                    <strong>{project.subcontractor}</strong>
                  </div>
                  <div>
                    <span>Site contact</span>
                    <strong>{project.siteContact || "No site contact added"}</strong>
                  </div>
                  <div>
                    <span>Quantity</span>
                    <strong>{project.quantity || "Quantity not set"}</strong>
                  </div>
                  <div>
                    <span>Crew</span>
                    <strong>{project.crewSize ? `${project.crewSize} people` : "Not set"}</strong>
                  </div>
                  <div>
                    <span>Invoice</span>
                    <strong>{project.invoiceNumber || "Draft"}</strong>
                  </div>
                </div>

                <div className="money-row wide">
                  <div>
                    <span>Contract</span>
                    <strong>{formatCurrency(project.contractAmount)}</strong>
                  </div>
                  <div>
                    <span>Paid</span>
                    <strong>{formatCurrency(project.paidAmount)}</strong>
                  </div>
                  <div>
                    <span>Balance</span>
                    <strong>{formatCurrency(getOpenBalance(project))}</strong>
                  </div>
                  <div>
                    <span>Task progress</span>
                    <strong>{progress.complete}/{progress.total}</strong>
                  </div>
                </div>

                <div className="project-controls-grid">
                  <label>
                    Move status
                    <select
                      value={project.status}
                      onChange={(event) => updateProjectStatus(project.id, event.target.value as ProjectStatus)}
                    >
                      {statusColumns.map((nextStatus) => (
                        <option key={nextStatus} value={nextStatus}>
                          {statusLabels[nextStatus]}
                        </option>
                      ))}
                    </select>
                  </label>

                  <label>
                    Log payment
                    <div className="inline-action">
                      <input
                        aria-label={`Payment amount for ${project.name}`}
                        type="number"
                        min="0"
                        step="100"
                        value={paymentDrafts[project.id] ?? ""}
                        onChange={(event) =>
                          setPaymentDrafts((current) => ({ ...current, [project.id]: event.target.value }))
                        }
                        placeholder="Amount"
                      />
                      <button type="button" onClick={() => recordPayment(project.id)}>
                        Save
                      </button>
                    </div>
                  </label>
                </div>
              </div>

              <aside className="project-side-panel">
                <section className="task-panel">
                  <div className="messages-header">
                    <strong>Things to do</strong>
                    <span>{progress.percent}% done</span>
                  </div>
                  <div className="task-list">
                    {getTasks(project).map((task) => (
                      <label className={`task-item ${task.complete ? "done" : ""}`} key={task.id}>
                        <input type="checkbox" checked={task.complete} onChange={() => toggleTask(project.id, task.id)} />
                        <span>
                          <strong>{task.title}</strong>
                          <small>{task.owner} - due {formatDate(task.dueDate)}</small>
                        </span>
                      </label>
                    ))}
                  </div>
                  <div className="inline-action add-task-row">
                    <input
                      aria-label={`New task for ${project.name}`}
                      value={taskDrafts[project.id] ?? ""}
                      onChange={(event) => setTaskDrafts((current) => ({ ...current, [project.id]: event.target.value }))}
                      placeholder={`Add ${roleOwner.toLowerCase()} task`}
                    />
                    <button type="button" onClick={() => addTask(project.id)}>
                      Add
                    </button>
                  </div>
                </section>

                <section className="document-panel">
                  <div className="messages-header">
                    <strong>Documents</strong>
                    <span>{getDocuments(project).length} files</span>
                  </div>
                  <label className="upload-dropzone">
                    <span>Upload plans, invoices, photos, lien waivers, or receipts</span>
                    <input
                      type="file"
                      multiple
                      accept="image/*,.pdf,.doc,.docx,.xls,.xlsx,.csv,.txt"
                      onChange={(event) => {
                        void uploadDocuments(project.id, event.target.files);
                        event.currentTarget.value = "";
                      }}
                    />
                  </label>
                  <div className="document-list">
                    {getDocuments(project).length === 0 ? (
                      <p className="empty-state compact">No documents uploaded yet.</p>
                    ) : (
                      getDocuments(project).map((document) => (
                        <article className="document-item" key={document.id}>
                          <div>
                            <strong>{document.name}</strong>
                            <small>
                              {formatFileSize(document.size)} - uploaded by {document.uploadedBy} {formatDateTime(document.uploadedAt)}
                            </small>
                          </div>
                          <div className="document-actions">
                            <a href={document.dataUrl} target="_blank" rel="noreferrer">
                              Open
                            </a>
                            <a href={document.dataUrl} download={document.name}>
                              Download
                            </a>
                            <button type="button" onClick={() => removeDocument(project.id, document.id)}>
                              Remove
                            </button>
                          </div>
                        </article>
                      ))
                    )}
                  </div>
                </section>

                <section className="messages">
                  <div className="messages-header">
                    <strong>Communication log</strong>
                    <span>{project.messages.length} entries</span>
                  </div>
                  <div className="message-list">
                    {project.messages.slice(0, 3).map((message) => (
                      <article key={message.id} className="message">
                        <div>
                          <strong>{message.sender}</strong>
                          <span>{formatDateTime(message.createdAt)}</span>
                        </div>
                        <p>{message.body}</p>
                      </article>
                    ))}
                  </div>
                  <label>
                    Add update as {roleMode === "contractor" ? "contractor" : "subcontractor"}
                    <textarea
                      value={messageDrafts[project.id] ?? ""}
                      onChange={(event) =>
                        setMessageDrafts((current) => ({ ...current, [project.id]: event.target.value }))
                      }
                      placeholder="Ask for schedule, mark a blocker, confirm completion, or add invoice details."
                      rows={3}
                    />
                  </label>
                  <button className="secondary-button" type="button" onClick={() => addMessage(project.id)}>
                    Add communication
                  </button>
                </section>
              </aside>
            </article>
          );
        })}

        {filteredProjects.length === 0 ? <p className="empty-state">No records match these filters.</p> : null}
      </section>
    </main>
  );
}

export default App;
