# Contributing

We welcome contributions from researchers, public health professionals, and food safety experts worldwide.

## How to Contribute

1. **Fork** the [repository](https://github.com/FSL-MQIP/salmonella-serovar-wiki)
2. **Create a branch** for your changes
3. **Add or update** serovar pages following the existing page structure
4. **Submit a pull request** with a description of your changes

## Guidelines

!!! tip "Consistency matters"
    Follow the existing eight-section structure for all serovar pages. See [About](index.md#serovar-page-structure) for the full section descriptions.

- **Cite all sources** in the **Relevant Links** section using numbered hyperlinks
- For **outbreaks**, always include: year, location, source, and case count
- For **border rejections**, include: year, exporting country, enforcing country, source, and product category
- Use [Wayback Machine](https://web.archive.org/) archived links for any expired URLs
- Use *italics* for species names (e.g., `*Salmonella*`) and gene names (e.g., `*gyrA*`)

## Adding a New Serovar

Create a new `.md` file in the appropriate serogroup directory under `docs/serovars/`. Use any existing serovar page as a template.

Serogroup directories:

| Directory | Serogroup |
|-----------|-----------|
| `group-a/` | O:2 (A) |
| `group-b/` | O:4 (B) |
| `group-c1/` | O:6,7 (C1) |
| `group-c2/` | O:8 (C2-C3) |
| `group-d/` | O:9 (D1) |
| `group-e/` | O:3,10 (E) |
| `other/` | All other serogroups |

After adding the file, update the group's `index.md` to include a link to the new page.

## Local Development

```bash
pip install -r requirements.txt
mkdocs serve
```

Then visit `http://127.0.0.1:8000` to preview your changes.

## Contact

For questions or to discuss contributions, contact [Martin Wiedmann](mailto:martin.wiedmann@cornell.edu).
