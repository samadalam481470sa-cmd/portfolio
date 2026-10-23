import { sampleProjects } from "./sampleData";
import type { Project } from "./types";

const STORAGE_KEY = "curb-connect-projects-v3";

export function loadProjects(): Project[] {
  try {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    return saved ? (JSON.parse(saved) as Project[]) : sampleProjects;
  } catch {
    return sampleProjects;
  }
}

export function saveProjects(projects: Project[]): void {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(projects));
}

export function resetProjects(): Project[] {
  window.localStorage.removeItem(STORAGE_KEY);
  return sampleProjects;
}
