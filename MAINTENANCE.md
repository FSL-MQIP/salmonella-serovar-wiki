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

## 3. How to Make Changes: Branching & PR Workflows

To protect the integrity of the live wiki, we use a `main` branch for the live site and a `dev` branch for all incoming changes. All changes must be submitted via a **Pull Request (PR)**. Direct pushes to `main` are blocked by a GitHub Ruleset.

### Workflow A: Content Edits (for Renato Orsi)

For text-only edits to Markdown (`.md`) files (e.g., serovar pages, homepage, resources) based on the biweekly digest or other verified sources.

1.  **Create Branch:** Create a new branch directly from the `main` branch (e.g., `renato/update-agona-outbreaks`).
2.  **Make Edits:** Edit the relevant `.md` files.
3.  **Open Pull Request:** Open a PR that merges your branch into `main`.
4.  **Self-Merge:** Since you are a project lead, you can **merge your own PR immediately** without waiting for another review. The PR is primarily for maintaining a clear audit trail of all changes to the `main` branch.

### Workflow B: Content Edits (for All Other Contributors)

For any content suggestions or edits from lab members.

1.  **Create Branch:** Create a new branch from the `dev` branch (e.g., `jane/fix-typo-heidelberg`).
2.  **Make Edits:** Edit the relevant `.md` files.
3.  **Open Pull Request:** Open a PR that merges your branch into the `dev` branch.
4.  **Request Review:** Assign Renato Orsi or Martin Wiedmann as a reviewer. They will review the changes, provide feedback, and merge the PR into `dev`.
5.  **`dev` to `main`:** Periodically, a project lead will merge the `dev` branch into `main` to publish all accumulated changes.

### Workflow C: Technical & Structural Changes (for Luke Qian)

For any changes that involve code, configuration, or site-wide structure.

- **Examples:** Modifying `mkdocs.yml`, changing CSS stylesheets, updating automation scripts, or adding new MkDocs plugins.

1.  **Create Branch:** Create a new branch from the `dev` branch (e.g., `luke/add-search-plugin`).
2.  **Make Edits:** Implement the technical changes.
3.  **Open Pull Request:** Open a PR that merges your branch into the `dev` branch.
4.  **Review & Merge:** A project lead will review and merge the PR.

---

## 4. `main` Branch Protection Rules

The `main` branch is protected by a **GitHub Ruleset** to ensure stability and a clear history. This is why all changes must go through a pull request.

| Rule | What it Means |
|---|---|
| **Require a pull request** | No one can push code directly to `main`. This creates a formal record of every change. |
| **Require conversation resolution** | Any review comments on a PR must be marked as "resolved" before the PR can be merged. |
| **No force pushes** | The commit history of the `main` branch cannot be rewritten. |
| **No deletions** | The `main` branch itself cannot be accidentally deleted. |

Notably, we **do not require a formal approving review** from another person. This allows trusted leads like Renato to merge their own content update PRs (Workflow A) without getting blocked, while still benefiting from the safety and audit trail of the PR process.
