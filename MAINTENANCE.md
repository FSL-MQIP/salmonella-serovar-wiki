# Salmonella Serovar Wiki: Maintenance SOP

This document outlines the Standard Operating Procedure (SOP) for maintaining and updating the Salmonella Serovar Wiki. Its purpose is to ensure consistency, accuracy, and a clear audit trail for all changes.

---

## 1. Contributor Roles

| Role | Name(s) | Responsibilities |
|---|---|---|
| **Project Leads** | Martin Wiedmann, Renato Orsi | Overall project direction, content accuracy, and final approval authority. |
| **Technical Lead** | Luke Qian | Manages the wiki's technical infrastructure, including site configuration (`mkdocs.yml`), custom styling (CSS), and any automation scripts. |
| **Content Contributors** | Lab Members | Update and enrich serovar pages, data sources, and other content based on new research and data. |

---

## 2. Core Maintenance Workflow: Biweekly Digest

A core part of our maintenance process is a biweekly digest of new scientific literature and public health news, powered by an OpenClaw AI assistant.

1.  **Digest Generation:** Every two weeks, the assistant automatically scans for new papers, outbreak reports, and news related to *Salmonella* serovars.
2.  **Email Delivery:** It sends a summary email to Martin Wiedmann and Renato Orsi. This email includes verified source links and suggested changes for the wiki.
3.  **Action & Triage:** Renato Orsi is responsible for reviewing the digest, triaging the suggestions, and initiating the content update process as described in the workflows below.

---

## 3. How to Make Changes: Branch Workflows

We use two long-lived branches: `main` (the live public site) and `dev` (the staging branch for all incoming changes). No new feature branches are needed — all contributors work directly on one of these two branches.

### Workflow A: Content Edits (Renato Orsi only)

For text-only edits to Markdown (`.md`) files — serovar pages, homepage, resources — based on the biweekly digest or other verified sources.

1. **Edit directly on `main`:** Renato can commit changes directly to the `main` branch without opening a pull request.
2. **Commit message:** Use a clear, descriptive commit message (e.g., `Update Typhimurium: add 2025 outbreak data`).

### Workflow B: Content Edits (All Other Lab Members)

For any content suggestions or edits from lab members.

1. **Edit directly on `dev`:** Make changes to the relevant `.md` files on the `dev` branch.
2. **Notify a project lead:** Let Renato Orsi or Martin Wiedmann know your changes are ready for review.
3. **Project lead merges `dev` → `main`:** After reviewing the changes on `dev`, a project lead opens a pull request from `dev` into `main` and merges it to publish the updates.

### Workflow C: Technical & Structural Changes (Luke Qian)

For any changes that involve code, configuration, or site-wide structure (e.g., `mkdocs.yml`, CSS stylesheets, automation scripts).

1. **Edit directly on `dev`:** Make all technical changes on the `dev` branch.
2. **Notify a project lead:** Let Renato Orsi or Martin Wiedmann know the changes are ready.
3. **Project lead merges `dev` → `main`:** A project lead reviews and opens a pull request from `dev` into `main` to publish the updates.

---

## 4. `main` Branch Protection Rules

The `main` branch is protected by a **GitHub Ruleset** to ensure stability and a clear history.

| Rule | What it Means |
|---|---|
| **Require a pull request** | Only Renato (Workflow A) can push directly to `main`. All other changes must come through a PR from `dev`. |
| **Require conversation resolution** | Any review comments on a PR must be marked as "resolved" before the PR can be merged. |
| **No force pushes** | The commit history of `main` cannot be rewritten. |
| **No deletions** | The `main` branch itself cannot be accidentally deleted. |

We do **not** require a formal approving review from another person, which allows project leads to merge `dev` → `main` PRs without being blocked when working independently.
