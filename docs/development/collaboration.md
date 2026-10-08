# Maintainer agreement

!!! note "Status: draft until both maintainers approve it"
    This agreement takes effect when **both** maintainers approve the pull request that adds
    it. A GitHub approval counts as a signature. It can be changed the same way. It is a
    working agreement between two friends, not a legal contract.

**Maintainers**

| Name | GitHub | Current track |
|---|---|---|
| Venkata Sai Karthik | [@EVSGoud](https://github.com/EVSGoud) | Track 2: data backbone |
| Krishna Nandimandalam | [@kclectic0501](https://github.com/kclectic0501) | Track 1: statistics engine |

Tracks are defined in the [work plan](workplan.md).

## 1. Ownership

1. We are **equal co-owners** of EvalHawk: the code, the name, the GitHub organization
   [`evalhawk`](https://github.com/evalhawk) and the PyPI project.
2. Both of us are **Owners** of the GitHub organization and of the PyPI project. Neither of
   us removes the other or changes the other's access.
3. The code is released under the [MIT License](https://github.com/evalhawk/evalhawk/blob/main/LICENSE)
   with both our names on the copyright line. Everything either of us contributes is under
   the same license.

## 2. Roles: track owners

1. Each of us **owns a track**: responsible for its design, code, tests, docs and dev-log
   entries, and the first person to ask about it.
2. Owning a track is **not exclusive**. Either of us may change any part of the code, through a
   pull request that the track owner reviews.
3. Tracks **rotate**. At each new stage we swap or re-split work so that both of us learn
   every part of the system (see the work plan).

## 3. How we decide

| Kind of decision | Who decides | How |
|---|---|---|
| Inside your own track, easy to reverse | The track owner | In the pull request |
| Affects both tracks, or hard to undo (a "one-way door") | **Both** | An [ADR](../decisions/index.md) that both approve |
| New runtime dependency | **Both** | An ADR |
| Releases, repo settings, PyPI | **Both** | Agreed in writing (issue or PR) before acting |

**When we disagree:**

1. Each writes the argument down in the PR or ADR, not just in chat.
2. If still stuck, a 30-minute call.
3. If still stuck: **measure** where possible (benchmark, simulation, prototype both), and
   otherwise choose the option that is **easier to reverse**.
4. Nothing contested gets merged until we agree.

## 4. Workflow

1. **Every task starts as a GitHub issue** (from the work plan), assigned to its owner.
2. Work on a **branch** (`feat/…`, `fix/…`, `docs/…`), never directly on `main`.
3. Open a **pull request** using the template. CI must be green.
4. The **other maintainer reviews** within **48 hours**, or says when they can.
5. **Squash-merge** once approved. The full rules are in the
   [engineering standards](standards.md).

## 5. Reviewing

1. **Approving means "I understand this and could explain it."** It doesn't mean "looks fine".
2. Ask questions freely. "Can you explain this line?" is always a fair review comment.
3. Review the tests first: they define what "correct" means.
4. Be kind and specific. Critique the code, not the person.

## 6. Using AI (Claude Code)

We both use Claude Code. The shared project instructions are in `CLAUDE.md` at the repo
root, so both assistants follow the same rules.

1. **You must be able to explain every line you submit.** "The AI wrote it" is not an
   explanation.
2. **The human checks the tests.** Tests decide what correct means, so read and understand
   every assertion.
3. **Say how AI was used** in the PR (the template has a section for it).
4. **Never** paste secrets, API keys or private data into an AI tool.
5. The AI **never pushes or merges** on its own. A human reviews first.
6. Stay inside your task. If your AI needs to change files in the other track, say so in
   the PR and tag the other maintainer.

## 7. Documentation duties

| When | What | Who |
|---|---|---|
| Starting a task | The GitHub issue (from the work plan) | Already drafted |
| Every PR | "What I learned" and "How AI was used" sections | The author |
| Every finished task | A short [dev-log](../devlog/index.md) entry | The task owner |
| Every one-way-door decision | An ADR | Whoever proposes it |
| Every user-visible change | A CHANGELOG line | The author |

## 8. Communication

1. **Weekly sync, 30 minutes:** what's done, what's next, what's blocking.
2. **Teach-back:** after the third task of each track, the owner explains their concepts to
   the other in 15 minutes.
3. **Decisions live in GitHub** (issues, PRs, ADRs), not only in chat, so we can find them later.
4. If you'll be unavailable for more than a week, tell the other in advance.

## 9. Credit

1. Both of us may present the **whole project** in portfolios, CVs and interviews.
2. When describing who built what, be accurate: name your own tracks and tasks. The git
   history and dev log show it anyway.
3. The README lists both maintainers equally.
4. Joint write-ups (such as the Phase 6 study) name both authors.

## 10. Time and leaving

1. Each of us writes down roughly how many hours per week we can give, and updates it when
   it changes: Karthik: ___ h/week · Krishna: 10 h/week.
2. Either of us may step back at any time. Please give notice and hand over open work
   (push your branch, update the issue).
3. Someone who leaves **stays credited** as a maintainer and author. The code stays MIT.
   Organization and PyPI access remain with whoever continues, unless we agree otherwise
   in writing.

## 11. Money

No money is expected. If EvalHawk ever earns anything (sponsorships, a company, paid work
based on it), the default is an **equal split**, and we write a new agreement **before**
accepting any money.

## 12. Changing this agreement

Open a PR that edits this page. It changes when both maintainers approve.

## Sign-off

- [ ] Venkata Sai Karthik approved the PR adding this agreement
- [x] Krishna Nandimandalam approved the PR adding this agreement
