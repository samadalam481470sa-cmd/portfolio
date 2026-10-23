# Curb Connect

Curb Connect is a contractor/subcontractor project tracker for curb and site concrete work. It helps a contractor communicate scopes that have not started, are started, are finished, or are paid complete while keeping payment records and job notes together.

## Features

- Project board grouped by status: Not started, Started, Finished, Complete
- Scope options for standard curbs, cut curbs, washouts, retaining walls, sidewalk tie-ins, ADA ramps, demo/haul-off, and other work
- Contractor and subcontractor role switcher with different dashboards for each side
- Rolling horizontal job strip that works well on phones and keeps jobs from feeling cramped
- Project creation form with dates, priority, location, site contact, crew size, quantity/footage, invoice number, contract amount, and notes
- Owner-specific task checklist so contractors and subcontractors can track their own things to do
- Document upload area for plans, invoices, photos, lien waivers, receipts, and closeout paperwork
- Open and download links for each uploaded job document
- Payment logging with paid totals, open balance, and automatic paid-complete closeout when a finished job is fully paid
- Search and filters by scope, status, contact, invoice, and job details
- Browser local storage persistence with demo data reset

## Getting started

Install dependencies:

```bash
npm install
```

Run the development server:

```bash
npm run dev
```

Build for production:

```bash
npm run build
```

Run checks:

```bash
npm run lint
npm test
```

## Notes

This first version is a front-end MVP that stores records in the browser. A production multi-user version should add authentication, a shared database, file uploads for invoices/photos, and role-based permissions for contractors and subcontractors.
