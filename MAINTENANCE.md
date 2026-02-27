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

1. **Digest Generation:** Every two weeks, the assistant automatically scans for new papers, outbreak reports, and news related to *Salmonella* serovars.
2. **Email Delivery:** It sends a summary email to Martin Wiedmann and Renato Orsi. This email includes verified source links and suggested changes for the wiki.
3. **Action & Triage:** Renato Orsi is responsible for reviewing the digest, triaging the suggestions, and initiating the content update process as described in the workflows below.

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
2. **Open a Pull Request:** Open a PR from `dev` into `main` and assign Renato Orsi or Martin Wiedmann as reviewer. See [Section 5.3](#53-how-to-open-a-pull-request) for step-by-step instructions.
3. **Project lead reviews and merges:** The assigned project lead reviews the changes, requests any revisions, and merges the PR to publish the updates.

### Workflow C: Technical & Structural Changes (Luke Qian)

For any changes that involve code, configuration, or site-wide structure (e.g., `mkdocs.yml`, CSS stylesheets, automation scripts).

1. **Edit directly on `dev`:** Make all technical changes on the `dev` branch.
2. **Open a Pull Request:** Open a PR from `dev` into `main` and assign Renato Orsi or Martin Wiedmann as reviewer. See [Section 5.3](#53-how-to-open-a-pull-request) for step-by-step instructions.
3. **Project lead reviews and merges:** The assigned project lead reviews the changes and merges the PR to publish the updates.

---

## 4. `main` Branch Protection Rules

The `main` branch is protected by a **GitHub Ruleset** to ensure stability and a clear history.

| Rule | What it Means |
|---|---|
| **Require a pull request** | Only Renato (Workflow A) can push directly to `main`. All other changes must come through a PR from `dev`. |
| **Require conversation resolution** | Any review comments on a PR must be marked as "resolved" before the PR can be merged. |
| **No force pushes** | The commit history of `main` cannot be rewritten. |
| **No deletions** | The `main` branch itself cannot be accidentally deleted. |

We do **not** require a formal approving review count, which allows project leads to merge `dev` → `main` PRs efficiently without being blocked.

---

## 5. Step-by-Step Procedures

### 5.1 Editing a Page Directly on GitHub (Online)

This is the easiest method for small text edits and requires no local software. It is the recommended approach for Workflow A and B contributors making simple changes.

1. Navigate to the repository on GitHub: `https://github.com/FSL-MQIP/salmonella-serovar-wiki`
2. Make sure you are on the correct branch. Use the branch selector dropdown (top-left of the file browser) to switch to `main` (Renato) or `dev` (all others).
3. Browse to the file you want to edit inside the `docs/` folder (e.g., `docs/serovars/group-b/typhimurium.md`).
4. Click the **pencil icon** (✏️) in the top-right corner of the file view to open the editor.
5. Make your edits. You can click the **"Preview"** tab at the top of the editor to see a rendered preview of the Markdown before saving.
6. When finished, scroll to the bottom of the page to the **"Commit changes"** section. Write a clear, descriptive commit message summarising what you changed (e.g., `Add 2024 Typhimurium outbreak in Canada`).
7. Click **"Commit changes"** to save directly to the branch.

> **Note:** Images and tables can be tricky to edit in the online editor. For complex edits involving tables or new sections, consider editing locally (see Section 5.2).

---

### 5.2 Editing Pages Locally

Local editing is recommended for larger changes, adding tables, or when you want to preview the full rendered site before committing.

**Prerequisites:** Install [Git](https://git-scm.com/downloads), a code editor (e.g., [VS Code](https://code.visualstudio.com/)), Python 3, and MkDocs Material.

```bash
# Install MkDocs and required plugins (one-time setup)
pip install -r requirements.txt
```

**Step-by-step:**

1. **Clone the repository** (one-time setup):
   ```bash
   git clone https://github.com/FSL-MQIP/salmonella-serovar-wiki.git
   cd salmonella-serovar-wiki
   ```

2. **Switch to the correct branch.** Renato uses `main`; all others use `dev`:
   ```bash
   git checkout dev        # for lab members and Luke
   git checkout main       # for Renato only
   ```

3. **Pull the latest changes** before starting to edit (important to avoid conflicts):
   ```bash
   git pull
   ```

4. **Make your edits** using your code editor. All content pages are in the `docs/` folder.

5. **Preview the site locally** to verify your changes render correctly:
   ```bash
   mkdocs serve
   ```
   Then open `http://127.0.0.1:8000` in your browser. The site will auto-refresh as you save files.

6. **Commit and push your changes:**
   ```bash
   git add .
   git commit -m "Your descriptive commit message here"
   git push
   ```

---

### 5.3 How to Open a Pull Request

Pull Requests (PRs) are used by lab members (Workflow B) and Luke (Workflow C) to submit changes from `dev` for a project lead to review and merge into `main`.

1. Go to the repository on GitHub: `https://github.com/FSL-MQIP/salmonella-serovar-wiki`
2. GitHub will often show a yellow banner saying **"dev had recent pushes"** with a **"Compare & pull request"** button — click it. If not, click the **"Pull requests"** tab, then **"New pull request"**.
3. Set the **base branch** to `main` and the **compare branch** to `dev`.
4. Write a clear **title** and **description** for your PR explaining what was changed and why.
5. On the right sidebar, click **"Reviewers"** and assign **Renato Orsi** or **Martin Wiedmann**.
6. Click **"Create pull request"**.
7. The assigned reviewer will be notified by email. They will review the changes, leave comments if needed, and merge the PR when satisfied.

> **Note:** All review comments must be resolved before a PR can be merged (enforced by the branch ruleset). If a reviewer leaves a comment, address it and mark the thread as "resolved".

---

### 5.4 Markdown Formatting Quick Reference

All wiki pages use [MkDocs Material](https://squidfunk.github.io/mkdocs-material/) flavoured Markdown. Below are the most commonly used formatting patterns in this wiki.

**Section headers:**
```markdown
## Background Information
### Subsection
```

**Tables:**
```markdown
| Column 1 | Column 2 | Column 3 |
|---|---|---|
| Value A  | Value B  | Value C  |
```

**Links:**
```markdown
[Link text](https://example.com)
```

**Admonition blocks** (used for "At a Glance"):
```markdown
!!! info "At a Glance"

    | Property | Value |
    |---|---|
    | Antigenic Formula | `1,4,[5],12:i:-` |
```

**Superscript footnotes:**
```markdown
Poultry is the primary reservoir.<sup>1</sup>
```

**Avoid using** `:a:`, `:b:`, `:m:`, `:o:`, `:x:` in plain text — these are interpreted as emoji shortcodes. If an antigenic formula contains these patterns (e.g., `:b:`), wrap the formula in backticks: `` `1,4,[5],12:b:-` ``.

---

### 5.5 Content Style Guidelines

Consistent style across serovar pages makes the wiki more professional and easier to maintain. Follow these conventions when writing or editing content.

- **Tense:** Use present tense for general facts ("*S.* Typhimurium is the most common serovar...") and past tense for specific historical events ("In 2008, an outbreak was linked to...").
- **Serovar names:** Always italicise the genus abbreviation: *S.* Typhimurium, *S.* Enteritidis.
- **Citations:** Add numbered superscript footnotes (`<sup>N</sup>`) inline and list the full references at the bottom of the page under `## References`.
- **URLs in links:** If a URL contains parentheses (common in NCBI and PMC links), wrap the URL in angle brackets to prevent rendering issues: `[Author et al.](<https://pmc.ncbi.nlm.nih.gov/...>)`.
- **Tables:** All tables must have a header row and a separator row (`|---|---|`). Do not use bold (`**text**`) inside table header cells.
- **At a Glance block:** Do not edit the At a Glance admonition block at the top of serovar pages manually. If the antigenic formula or serogroup needs updating, also update the corresponding text in the Background Information section to keep them consistent.
