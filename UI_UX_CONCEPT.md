# LeLinc Unified Chat — UI/UX Concept & Build Plan

**Prepared for:** Garry (Key View Pty Limited) & Q
**Product:** LeLinc Unified Chat (unified inbox + multi-agent chat)
**Current state:** Basic dark-mode chat UI exists in chat.html. This document evolves it into a polished, premium, production-ready experience.

---

## Table of Contents

1. [Design Direction](#1-design-direction)
2. [Key Screens Design](#2-key-screens-design)
3. [UX Flow — Complete Journey Map](#3-ux-flow--complete-journey-map)
4. [Interaction Patterns](#4-interaction-patterns)
5. [Design Principles for the UI Specialist](#5-design-principles-for-the-ui-specialist)
6. [Priority Build Roadmap](#6-priority-build-roadmap)

---

## 1. Design Direction

### 1.1 Visual Philosophy

**"Dark premium, approachable, chat-first."**

The product is a chat window before it's a SaaS dashboard. Every design decision should answer: *"Does this make the chat feel more natural, more trustworthy, or more effortless?"*

We're aiming for the visual feel of **Linear's dark mode** (precision, space, glow accents) crossed with **WhatsApp's simplicity** (chat is the entire screen, no chrome). The result should feel secure and professional without being cold.

### 1.2 Color Palette (Refined)

The existing palette is solid — we refine, not replace.

| Token | Current | Refined | Usage |
|-------|---------|---------|-------|
| `--bg` | `#0b0b0f` | `#0a0a0e` | Chat background, page background |
| `--surface` | `#14141a` | `#121218` | Header, input bar, cards, modals |
| `--surface2` | `#1c1c26` | `#1a1a24` | Incoming message bubbles, secondary surfaces |
| `--surface3` | *(none)* | `#22222e` | Hover states, pressed states |
| `--border` | `#2a2a36` | `#2a2a3a` | Dividers, card borders |
| `--border-subtle` | *(none)* | `#1e1e2a` | Very subtle separators |
| `--text` | `#e8e8ee` | `#eeeeee` | Primary body text |
| `--text2` | `#8888a0` | `#9a9ab0` | Secondary/tertiary text, timestamps |
| `--text3` | *(none)* | `#6a6a82` | Placeholder text, disabled states |
| `--accent` | `#6c5ce7` | `#7c6cf0` | Primary accent (slightly brighter for better contrast) |
| `--accent-hover` | *(none)* | `#8d7df5` | Button hover states |
| `--accent-glow` | `rgba(108,92,231,0.3)` | `rgba(124,108,240,0.25)` | Glow effects, focus rings |
| `--accent-subtle` | *(none)* | `rgba(124,108,240,0.10)` | Subtle accent backgrounds |
| `--success` | `#00e676` | `#00e676` | Online status, confirmed actions |
| `--warning` | `#ffc107` | `#ffc107` | Unread counts, attention needed |
| `--danger` | `#ff5252` | `#ff5252` | Errors, disconnection |
| `--incoming` | `#1c1c26` | `#1a1a24` | Incoming message bubble background |
| `--outgoing` | `#6c5ce7` | `#7c6cf0` | Outgoing message bubble background |

**Additional semantic tokens:**

```css
--platform-whatsapp: #25d366;
--platform-telegram: #0088cc;
--platform-instagram: #e4405f;
--platform-linkedin: #0a66c2;
--platform-webchat: var(--accent);

--agent-cosidekick: #7c6cf0;
--agent-cfo: #00bcd4;
--agent-prsales: #ff6f00;
--agent-q: #e040fb;
```

### 1.3 Typography

**System font stack (no external fonts needed — this is mobile-first and every millisecond matters):**

```css
font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'SF Pro Text',
             'Segoe UI Variable', 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
```

**Type scale (mobile-first, rem-based):**

| Token | Size | Weight | Line Height | Usage |
|-------|------|--------|-------------|-------|
| `--text-xs` | 0.65rem (10.4px) | 400 | 1.3 | Timestamps, badges, footnotes |
| `--text-sm` | 0.75rem (12px) | 400 | 1.4 | Secondary labels, status text |
| `--text-base` | 0.875rem (14px) | 400 | 1.45 | Message body, input text |
| `--text-lg` | 1rem (16px) | 500 | 1.4 | Agent name in header, list items |
| `--text-xl` | 1.15rem (18.4px) | 600 | 1.3 | Welcome heading |
| `--text-2xl` | 1.35rem (21.6px) | 700 | 1.25 | Page titles, modals |

**Key rule:** Never go below 10px. On mobile, text must be comfortably readable without zooming.

### 1.4 Spacing System

Four-step vertical rhythm:

```css
--space-1: 4px;
--space-2: 8px;
--space-3: 12px;
--space-4: 16px;
--space-5: 20px;
--space-6: 24px;
--space-8: 32px;
--space-10: 40px;
```

**Key measurements:**
- **Chat padding (sides):** 12px (mobile), 16px (tablet+)
- **Message gap:** 4px (consecutive messages from same sender), 12px (between different senders)
- **Bubble padding:** 10px 14px
- **Header height:** 56px (including status row)
- **Input bar height:** 58px (plus safe-area bottom padding)
- **Max bubble width:** 82% on mobile, 70% on desktop

### 1.5 Border Radius

```css
--radius-sm: 8px;
--radius-md: 12px;
--radius-lg: 16px;
--radius-xl: 20px;
--radius-full: 9999px;
```

**Message bubbles:**
- Incoming: `--radius-md` with `border-bottom-left-radius: 4px` (chat asymmetry)
- Outgoing: `--radius-md` with `border-bottom-right-radius: 4px`
- Date separators: `--radius-full` (pill shape)

### 1.6 Shadows & Glows

```css
--shadow-sm: 0 1px 2px rgba(0,0,0,0.3);
--shadow-md: 0 4px 12px rgba(0,0,0,0.4);
--shadow-lg: 0 8px 24px rgba(0,0,0,0.5);
--shadow-xl: 0 12px 40px rgba(0,0,0,0.6);
--glow-accent: 0 0 16px rgba(124,108,240,0.15);
--glow-success: 0 0 12px rgba(0,230,118,0.12);
```

### 1.7 Animations & Transitions

```css
/* Duration tokens */
--duration-fast: 150ms;
--duration-normal: 250ms;
--duration-slow: 400ms;

/* Easing */
--ease-out: cubic-bezier(0.16, 1, 0.3, 1);
--ease-in-out: cubic-bezier(0.65, 0, 0.35, 1);
--ease-spring: cubic-bezier(0.34, 1.56, 0.64, 1);
```

**Animation patterns:**
- Message entrance: fadeIn + slideUp (200ms, ease-out)
- Handoff banner: slideDown (300ms, ease-out), auto-dismiss after 4s
- Typing dots: continuous bounce (1.4s cycle)
- Button press: scale(0.95) on `:active`
- Page/panel transitions: slide from right (250ms, ease-in-out)
- Status changes: crossfade (200ms)

---

## 2. Key Screens Design

### 2.1 Onboarding Flow — "Link to Chat in 3 Taps"

#### Screen 1: Landing Page (Mobile Web)

**Layout (top to bottom):**

```
┌─────────────────────────────────────┐
│                                       │
│        [Large subtle logo]            │
│                                       │
│   "What does your business need?"     │
│                                       │
│   ┌─────────────────────────────┐     │
│   │  🌐  Website & hosting      │     │
│   └─────────────────────────────┘     │
│   ┌─────────────────────────────┐     │
│   │  💼  Business restructuring  │     │
│   └─────────────────────────────┘     │
│   ┌─────────────────────────────┐     │
│   │  📱  Social media & ads     │     │
│   └─────────────────────────────┘     │
│                                       │
│   [Small text: "Powered by LeLinc"]   │
│                                       │
└─────────────────────────────────────┘
```

**Design specs:**
- Big emoji icons (1.5rem) with subtle 2-line description below each option
- Cards: surface background, 1px border, 12px radius, 12px padding
- Selected state: accent border + subtle glow
- No login, no password. This is the full form.
- After selection, a simple inline form animates in (name + email + business name), 3 fields max

**User action:** Taps one card → fills 3 fields → taps "Get Started"

#### Screen 2: QR Code / Link Screen

```
┌─────────────────────────────────────┐
│  ← Back                 [••• menu]  │
│                                       │
│         ✓ Session created             │
│                                       │
│         ┌───────────┐                │
│         │           │                │
│         │  QR CODE  │                │
│         │           │                │
│         └───────────┘                │
│                                       │
│    "Scan to start chatting"           │
│                                       │
│    [Copy Link] [Share] [SMS]          │
│                                       │
│  ─────────────────────────────────    │
│                                       │
│    Your chat is ready at:             │
│    chat.keyview.com.au/xxxx          │
│                                       │
│    Or keep this page open             │
│    and reply below:                   │
│                                       │
│    ┌───────────────── [Send] ─┐      │
│    │ Type a message...        │      │
│    └──────────────────────────┘      │
│                                       │
└─────────────────────────────────────┘
```

**Design specs:**
- QR code centered, 200×200px, with subtle white border
- Below: 3 action buttons in a row (Copy Link, Share, SMS)
- Below the fold: A mini chat input — the client can start typing **right here** on the landing page. This is the key innovation: **no phone scan required to start chatting.** The QR code screen doubles as a web chat entry point.
- The chat opens inline on the same page (or slides in as a panel)

**Key UX principle:** Don't force mobile scanning if the client is already on their phone. The QR is for cross-device (desktop → phone). The chat should start immediately from this page.

#### Screen 3: Welcome Flow (First Chat Open)

```
┌─────────────────────────────────────┐
│  [←]  [Avatar 🦊] CoSidekick  [⚙]  │
│                    ● Online          │
│──────────────────────────────────────│
│                                       │
│               ┌─────────┐            │
│               │ Dec 12  │            │
│               └─────────┘            │
│                                       │
│  ┌────────────────────────────┐      │
│  │ 👋 Hey! I'm CoSidekick.    │      │
│  │                            │      │
│  │ I can help you with:       │      │
│  │ • Website speed fixes       │      │
│  │ • Hosting migration         │      │
│  │ • Domain management         │      │
│  │ • Tech support              │      │
│  │                            │      │
│  │ What's the first thing     │      │
│  │ you need help with? 👇    │      │
│  └────────────────────────────┘      │
│                                       │
│  ┌──────────────────── [Send] ─┐     │
│  │ Type a message...           │      │
│  └─────────────────────────────┘     │
│                                       │
└─────────────────────────────────────┘
```

**Design specs:**
- Agent avatar: 40px circle with gradient background (agent-colored). Emoji or initial inside.
- Agent name in header matches the assigned agent
- Connection status dot: green (online), yellow (connecting), red (offline)
- Welcome message: first message from agent, formatted as incoming bubble with soft intro
- No loading spinners — the chat should be interactive immediately

---

### 2.2 Chat Interface — The Core Screen

This is the screen the user spends 99% of their time on. It must feel as effortless as WhatsApp.

```
┌─────────────────────────────────────┐
│  [←]  [Avatar 🦊] CoSidekick  [⚙]  │
│          ● Online  • via Web Chat   │
│──────────────────────────────────────│
│                                       │
│               ┌─────────┐            │
│               │ Dec 12  │            │
│               └─────────┘            │
│                                       │
│  ┌────────────────────────────┐      │
│  │ 👋 Hey! I'm CoSidekick.    │      │
│  │ Need help with hosting?    │      │
│  │                   12:30pm  │      │
│  └────────────────────────────┘      │
│                                       │
│       ┌─────────────────────────┐    │
│       │ My website is loading   │    │
│       │ really slow. Can you    │    │
│       │ check it?               │    │
│       │               12:31pm   │    │
│       └─────────────────────────┘    │
│                                       │
│  ┌────────────────────────────┐      │
│  │ Absolutely! What's your    │      │
│  │ domain name? I'll run a    │      │
│  │ quick speed audit.         │      │
│  │           12:31pm  ✓✓      │      │
│  └────────────────────────────┘      │
│                                       │
│  [---- Agent Change ----]             │
│  ┌────────────────────────────┐      │
│  │ 🧾 Hi! CoSidekick handed   │      │
│  │ your billing question to   │      │
│  │ me. I'm the CFO Agent.     │      │
│  │ Let me look at your plan.  │      │
│  │                   12:32pm  │      │
│  └────────────────────────────┘      │
│                                       │
│  ┌──┐                               │
│  │●●│ CoSidekick is typing...       │
│  └──┘                               │
│                                       │
│──────────────────────────────────────│
│  ┌────────────────────── [Send] ─┐   │
│  │ Type a message...    📎 🎤    │   │
│  └───────────────────────────────┘   │
│                                       │
└─────────────────────────────────────┘
```

#### Message Bubble Specs (Refined from Current)

**Incoming message (agent):**
- Background: `--surface2` (#1a1a24) with 1px `--border` (#2a2a3a)
- Radius: 12px top-left+top-right+bot-right, 4px bot-left
- Max-width: 82% mobile / 70% desktop
- Sender label: shown only on first message from a new sender (or after a gap), 0.65rem, agent accent color
- Timestamp: bottom-right, 0.6rem, `--text3`, on its own line
- Padding: 10px 14px
- Read receipts: shown only on outgoing

**Outgoing message (client):**
- Background: `--accent` (#7c6cf0)
- Radius: 12px top-left+top-right+bot-left, 4px bot-right
- Color: white
- Timestamp: bottom-right, 0.6rem, white at 60% opacity
- Read status: "✓" (delivered) or "✓✓" (read), next to timestamp
- Padding: 10px 14px

**System message (agent change, date separator, connection notice):**
- Centered, full-width
- Background: transparent or subtle pill
- Color: `--text2`
- Font-size: 0.7rem
- Agent change: pill-shaped, subtle accent border, with animated entrance
- Date separator: pill with `--surface` background, small text

#### Header Specs

**Left side:**
- Back button (only when the chat is inside the dashboard context)
- Agent avatar: 36px circle, gradient background based on agent identity
- Agent name + status row

**Status row format:**
```
● Online  •  via WhatsApp
```
- Dot: green/red/yellow
- Platform: "via WhatsApp" / "via Web Chat" / "via Telegram"
- Platform indicator: colored dot matching platform brand color

**Right side:**
- Settings/options icon (gear or three dots)
- Tapping opens a bottom sheet

#### Platform Badge (subtle indicator)

**Concept:** A tiny pill badge below or next to the agent name showing which platform is bridging the message.

**Options:**

1. **In header** (recommended for simplicity):
   ```
   CoSidekick
   ● Online  •  via WhatsApp
   ```
   The "via WhatsApp" text is `--text2` with a small colored dot matching the platform brand.

2. **Per-message platform tag** (for multi-platform sessions):
   Each incoming message can optionally show a small platform icon in the top-right corner of the bubble.

3. **Connections bar** (collapsible, below header):
   Shows all active connections as small colored dots with platform icons. Tapping expands to show status.

**Platform colors:**
- WhatsApp: `#25d366` (green)
- Telegram: `#0088cc` (blue)
- Instagram: `#e4405f` (pink)
- LinkedIn: `#0a66c2` (blue)
- Web Chat: `--accent` (purple)

**Recommended approach:** Show in header only. Keep messages clean. The user doesn't need to know per-message routing — they just need to know "this chat is happening on WhatsApp."

---

### 2.3 Agent Handoff UX

**The problem:** When an AI agent hands off to another AI agent, the client must understand:
1. The conversation is continuing, not ending
2. A new specialist is now helping
3. The handoff reason (why this happened)
4. They don't need to do anything — the new agent has context

#### Visual Pattern: "Guard Change" Animation

```
┌─────────────────────────────────────┐
│                                       │
│  [last message from CoSidekick]       │
│                                       │
│  ── ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─   │
│                                       │
│  ┌─────────────────────────────────┐ │
│  │   🔄 Agent Change               │ │
│  │                                 │ │
│  │   CoSidekick  ──➤  CFO Agent   │ │
│  │                                 │ │
│  │   "Handing over your billing    │ │
│  │    questions"                   │ │
│  │                                 │ │
│  │   [continue chatting below]     │ │
│  └─────────────────────────────────┘ │
│                                       │
│  ── ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─   │
│                                       │
│  ┌────────────────────────────┐      │
│  │ Hi! I'm handling the       │      │
│  │ billing now. Your current  │      │
│  │ plan is...                 │      │
│  └────────────────────────────┘      │
│                                       │
└─────────────────────────────────────┘
```

**Design specs:**
- The handoff banner replaces the current system message approach
- It's a card with:
  - Left: agent avatar transition (old avatar fades, new avatar fades in)
  - Center: "CoSidekick → CFO Agent" with arrow animation
  - Bottom: reason text in `--text2`
- Top/bottom: subtle dotted or dashed separators (`--border`)
- Background: `--accent-subtle` (very faint purple glow)
- Auto-dismiss: fades out after 8 seconds, but stays in the message history as a system message
- Animation: the banner slides down, the arrow animates from left to right
- The header updates simultaneously (new agent name + avatar)
- Optional: haptic-like pulse on the new agent's avatar (CSS animation)

**Behind the agent change, the client sees:**
1. Old agent writes a final closing message (e.g., "Let me hand you to my colleague who handles billing")
2. Handoff banner appears
3. New agent writes an opening message with context ("Hi, I see you need help with billing...")
4. Header updates to new agent

**The key rule:** The conversation never pauses. The client should never feel like they're being "transferred." It should feel like a natural handover in a store: "Let me get my colleague who specializes in this."

---

### 2.4 Profile / Settings Screen

A bottom sheet or full-page overlay accessed from the header gear icon.

```
┌─────────────────────────────────────┐
│  My Chat Settings              [✕]  │
│──────────────────────────────────────│
│                                       │
│  ┌─────────────────────────────────┐ │
│  │  You're chatting with:          │ │
│  │  [Large agent avatar]           │ │
│  │  CoSidekick                     │ │
│  │  Key View Digital               │ │
│  │                                 │ │
│  │  [Agent info / capabilities]    │ │
│  └─────────────────────────────────┘ │
│                                       │
│  ─── Connected Platforms ───         │
│                                       │
│  🟢  WhatsApp          ● Active      │
│  🟡  Telegram          ● Connecting  │
│  🔴  Instagram         ● Disabled    │
│                                       │
│  ─── Session Info ───                │
│                                       │
│  Session ID: abc-123                 │
│  Created: Dec 12, 2024               │
│  Messages: 23                        │
│                                       │
│  🔒  End-to-end encrypted             │
│                                       │
│  ─── Actions ───                     │
│                                       │
│  [Download Chat History]             │
│  [Archive Conversation]              │
│  [Report an Issue]                   │
│                                       │
└─────────────────────────────────────┘
```

**Design specs:**
- Dark overlay behind the sheet (60% opacity)
- Sheet: 90% height, rounded top corners (20px), slides up
- Drag handle at top (thin pill, 32px wide, 4px tall)
- Agent card: large avatar (56px), business name, description
- Platform connections: icon + name + status + toggle
- Security: visible encryption badge communicates trust

---

### 2.5 Q's Overview Dashboard (Desktop)

This is the command center for the overseer — shows all active conversations across all products.

```
┌──────────────────────────────────────────────────────────────┐
│  LeLinc Unified — Overview                      Q Avatar     │
│──────────────────────────────────────────────────────────────│
│                                                               │
│  Active Conversations    │    Filters: [All] [KVD] [KVC] ... │
│                                                               │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │ Total Active: 12  │ Unread: 8  │ Agents: 4  │ Platforms │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                               │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │  [Search by client, email, business...]                   │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                               │
│  ─── Conversation List ───                                    │
│                                                               │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │ 🟢  Beauty Studio Co  │ 🦊 CoSidekick │ 2 unread  │🟡   │ │
│  │     "My website is loading slow..."   │ 2m ago           │ │
│  │     🌐 Web Chat                                           │ │
│  ├──────────────────────────────────────────────────────────┤ │
│  │ 🟢  Richo Diesel     │ 💰 CFO Agent   │ 0 unread  │🟢   │ │
│  │     "Invoice #1042 has been paid"     │ 15m ago          │ │
│  │     💬 WhatsApp                                           │ │
│  ├──────────────────────────────────────────────────────────┤ │
│  │ 🔴  Smith & Co Law   │ 📣 PR/Sales    │ 4 unread  │🔴   │ │
│  │     "Can you post to Instagram too?"  │ 1h ago           │ │
│  │     📱 Instagram DM                                       │ │
│  │     [⚠️ Needs attention — handoff requested]              │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                               │
│  ─── Priority Queue ───                                       │
│                                                               │
│  [Smith & Co — 4 unread] [Beauty Studio — 2 unread]          │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

**Design specs:**
- Desktop-first for this screen (Q works from a computer)
- 3-column layout on large screens, collapses to single column on tablet
- Left sidebar: nav with Products, Teams, Settings
- Center: conversation list (primary view)
- Right: detail pane when a conversation is selected
- Each conversation row shows:
  - Status indicator (green/pulse=active, yellow=idle, red=needs attention)
  - Client name + business
  - Current agent with colored badge
  - Unread count badge (warning color)
  - Last message preview (truncated to 1 line)
  - Platform indicator (icon + name)
  - Time ago
  - Urgency flag if handoff was requested or unread > threshold
- Search filters by client, agent, platform, product, status
- Real-time updates via WebSocket (rows animate in/out, unread counts increment)

---

## 3. UX Flow — Complete Journey Map

### Phase 1: First Touch (The Nail)

```
Marketing Channel ──> Landing Page ──> Select Need ──> Fill Form ──> Chat Opens
(ad, referral,     (lelinc.keyview     (tap card)     (name,         (immediately)
 QR code, search)   .com.au)                           email, biz)
```

**Key metrics at each step:**
1. Landing page load: < 1.5s
2. Card selection: 1 tap, instant
3. Form fill: 3 fields, < 30 seconds
4. Chat opens: instant (no loading screen)

### Phase 2: The Onboarding Conversation

```
Chat Opens ──> Welcome Message ──> Client Types ──> Agent Responds
(no delay)    (CoSidekick intro    (first question)  (< 3 seconds
              + suggested topics)                    perceived)
```

**The welcome message is critical.** It should:
- Introduce the agent by name
- List 3-5 things the agent can help with (bullet points)
- End with a question that invites a response
- Feel like a person, not a bot

### Phase 3: Active Conversation

```
Client Message ──> CDP Bridge ──> Message Store ──> Agent Reads ──> Agent Writes
     │                                                                   │
     └──────────── < 500ms round-trip for client ────────────────────────┘
```

### Phase 4: Agent Handoff

```
Agent A: "Let me get my billing colleague" ──> Handoff Trigger
    │                                              │
    │                                              ▼
    │                                    Kanban: Agent A -> Agent B
    │                                              │
    │                                              ▼
    │                                    System: Assign Agent B
    │                                              │
    └────────────────── Handoff Banner ────────────┘
                               │
                               ▼
                    Agent B writes with context
                               │
                               ▼
                    Conversation continues seamlessly
```

### Phase 5: Return / Ongoing Use

```
Client returns ──> Same chat URL ──> Sees history ──> Types ──> Agent continues
(bookmarked,      (no login           (scrollable)      (no     (with context
 QR scan,          needed)                              greeting from history)
 email link)                                            needed)
```

### Phase 6: Resolution

```
Task Complete ──> Agent: "All done!" ──> Summary Message ──> Session Archivable
                              │                                   │
                              ▼                                   ▼
                    "Is there anything else?"          Q can archive/resolve
```

---

## 4. Interaction Patterns

### 4.1 Real-Time Message Delivery

**Pattern: Optimistic UI with server confirmation**

1. Client taps Send → message appears in outgoing bubble **instantly** (no spinner)
2. Message shows "Sending..." or "◌" in the timestamp area
3. Server acknowledges (WebSocket echo) → "◌" becomes "✓" (delivered)
4. Agent reads → "✓✓" (read)
5. If server rejects (connection lost, session invalid) → bubble turns red with "✗ Failed" → tap to retry

**Timing targets:**
- Send → appear in UI: < 10ms (local)
- Send → delivered confirmation: < 200ms (WebSocket round-trip)
- Agent → client broadcast: < 100ms

### 4.2 Typing Indicators

**Pattern: Delayed show, immediate hide**

- When agent starts typing, show indicator after 300ms debounce (prevents flicker from rapid start/stop)
- Hide immediately when agent stops or message arrives
- Show agent name: "CoSidekick is typing..."
- On agent change during typing: update name smoothly

**Visual:** Three bouncing dots (5px circles, 3px gap, bounce animation with staggered delays)

### 4.3 Connection Status

**Three states:**

| State | Indicator | Header Dot | Behavior |
|-------|-----------|------------|----------|
| Connected | "Online" | Green (● `#00e676`) | Normal operation |
| Reconnecting | "Reconnecting..." | Yellow (● `#ffc107`) + pulsing | Messages queued locally, will send on reconnect |
| Disconnected | "Offline" | Red (● `#ff5252`) | Messages cannot be sent, retry button on failed sends |

**Reconnection behavior:**
- Attempt every 3 seconds (exponential backoff: 3s → 6s → 12s → max 30s)
- Show "Reconnecting..." in header
- Queue up to 50 messages locally (IndexedDB), flush on reconnect
- On reconnect: resend queued messages, sync message history from server
- No disruptive modals — the status indicator is subtle but clear

### 4.4 Error & Offline States

**Network error while sending:**
- Message bubble stays visible but gets a red tint + "✗ Failed" label
- A "↻ Retry" button appears next to the failed message
- Tapping retry re-sends via WebSocket
- No data loss — the message is stored locally until sent

**Session not found (invalid link):**
- Full-screen error state: centered icon (🔗 broken) + "This chat link is no longer valid" + "Contact your service provider"
- Clean, non-alarming. Not a 404 page.

**Server unavailable:**
- Inline banner below header: "Connection lost — messages will send when reconnected"
- Input bar stays active, typing still works, messages queued
- No full-screen takeover

**Agent offline / busy:**
- Show in typing area: "Agent is working on your request — replies may take a moment"
- Optional: estimated wait time if available

### 4.5 Agent Handoff Animation

**Detailed animation sequence:**

1. **Trigger:** Old agent sends final message → system detects handoff
2. **Banner entrance (300ms):** Banner slides down from below the last message. Dashed separator lines appear above and below it. The banner background fades in from 0 to `--accent-subtle`.
3. **Avatar transition (600ms):** Old agent avatar on the left fades out (200ms). A brief gap (100ms). New agent avatar fades in from bottom (300ms) with a subtle scale bounce.
4. **Arrow animation (400ms):** "CoSidekick → CFO" — the arrow line grows from left to right, with the new agent name appearing at the end.
5. **Header update (200ms):** Header agent name and avatar crossfade to the new agent.
6. **State message (instant):** System message is written to the database: "CoSidekick → handing over to CFO Agent"
7. **Banner auto-dismiss (8s):** After 8 seconds, the banner fades out (400ms), leaving only the system message in the history.
8. **New agent message:** Agent B's first message arrives, appearing as a new incoming bubble with the new agent's avatar.

---

## 5. Design Principles for the UI Specialist

### Principle 1: Mobile-First, Always

- Design at 375px width first. Expand to desktop.
- Touch targets: minimum 44×44px (buttons, send, back, avatar)
- Safe areas: respect `env(safe-area-inset-bottom)` on the input bar
- No hover-dependent interactions — everything works with tap
- Font sizes: never below 14px for body text, 10px for metadata
- The chat viewport is exactly the screen — no horizontal scroll, no toolbar chrome

### Principle 2: Dark Mode as Default

- Light mode is secondary, can be added later
- Use true black (`#000`) only sparingly — the `#0a0a0e` gives depth without being harsh
- Text contrast: `--text` (#eeeeee) on `--bg` (#0a0a0e) = ~17:1 contrast ratio (well above AA)
- Avoid pure white text on colored backgrounds — use `rgba(255,255,255,0.95)` for a softer white
- Shadows should be subtle — dark themes show heavy shadows easily

### Principle 3: Zero Clutter

**Every element on screen must answer: "Why am I here?"**

- The header shows: agent identity + connection status. That's it.
- The input bar shows: text field + send button. No unnecessary icons.
- Message bubbles show: content + timestamp. Sender name only when unclear.
- No "powered by" badges in the active chat area (footer is fine).
- No avatars next to every message (they add visual noise in rapid conversation).

**Remove if it doesn't serve the user:**
- Full message send/read timestamps (just show time)
- Profile photos on every incoming message (show once at top of thread or when sender changes)
- Scroll-to-bottom button (only show if user has scrolled up significantly)
- Attachment/camera buttons (add later if needed — start with text only)

### Principle 4: Feels Like Chatting, Not Like Using Software

- The entire screen is a conversation — no sidebar, no nav bar, no tabs
- Messages are the primary content — they should occupy 70%+ of the viewport
- Input bar is always visible and ready — no modals or redirects to send a message
- "Send" should feel like pressing Enter in WhatsApp, not submitting a form
- Agent responses should feel conversational, not templated
- Loading states should be invisible (optimistic UI) or charming (typing indicator)
- Sound cues optional: subtle "sent" and "received" sounds (toggleable in settings)

### Principle 5: Agent Persona Visible but Not Intrusive

- Agent identity is shown in the header at all times (name + avatar)
- Agent avatar updates smoothly on handoff
- Agent name appears as a label on the first incoming message of a new agent
- After that, the agent color/hue of the bubble is enough to identify continuity
- Each agent has a distinct emoji/icon and gradient color for quick visual recognition
- No chatbot "personality" animations (no bouncing avatars, no sparkles) — keep it professional

### Principle 6: Trust Signals

**Encryption:**
- Show a subtle lock icon + "End-to-end encrypted" text in the input bar area or profile sheet
- Not in the main chat view — it's background trust, not foreground distraction
- Accessible via the profile sheet for users who want confirmation

**Message history:**
- All messages persist (no auto-delete without user action)
- Scroll to load older messages — history is always accessible
- Download option in settings (export as .txt or .json)

**Privacy:**
- No "seen" timestamps for the client (reduces pressure)
- Read receipts are one-way (client can see their messages were read)
- Session link is unique + expiring (communicate this implicitly, not with scary warnings)

**Visual trust cues:**
- Clean, professional typography (no Comic Sans, no cartoon fonts)
- Consistent spacing (messages don't overlap or feel cramped)
- No sudden UI shifts (elements don't jump around when loading)
- Error messages are helpful, not technical: "Something went wrong" → "Your message couldn't be sent. Tap to retry."

---

## 6. Priority Build Roadmap

### Phase 1: Polish the Core Chat (This Week)
- Implement the refined color palette
- Add read receipts (✓ / ✓✓)
- Smooth animations on message entrance
- Connection status with yellow/red/green states
- Platform indicator in header ("via WhatsApp")
- Offline message queuing
- Touch-friendly input area (44px minimum targets)

### Phase 2: Agent Handoff UX (Next Week)
- Build the handoff banner with avatar transition animation
- Header agent crossfade
- Agent color scheme + avatars
- Handoff system messages as state transitions
- Auto-dismiss timer on banner

### Phase 3: Onboarding Flow (Week 3)
- Landing page redesign (card selection → form → chat)
- QR code screen with inline mini-chat
- Welcome message content strategy
- Session creation → chat redirect flow

### Phase 4: Profile & Settings (Week 4)
- Bottom sheet profile screen
- Platform connection status
- Session info display
- Export/download history
- Archive conversation

### Phase 5: Q's Overview (Week 5)
- Desktop dashboard layout
- Conversation list with search/filter
- Real-time updates
- Agent assignment display
- Unread count badge
- Priority queue

### Phase 6: Light Mode + Polish (Ongoing)
- Light color scheme (invert palette with warm white background)
- Sound cues (optional)
- Accessibility audit (contrast, screen reader support)
- Performance optimization (lazy loading history, virtual scrolling for 1000+ messages)

---

## Appendix: Agent Identity Specs

Each agent needs a distinct visual identity:

| Agent | Emoji | Gradient | Role | Color |
|-------|-------|----------|------|-------|
| CoSidekick | 🦊 | `#7c6cf0` → `#a78bfa` | Primary support, tech help | Purple |
| CFO Agent | 🧾 | `#00bcd4` → `#4dd0e1` | Billing, invoicing, financial | Cyan |
| PR/Sales | 📣 | `#ff6f00` → `#ffa726` | Marketing, social media | Orange |
| Q (Overseer) | 👁 | `#e040fb` → `#ea80fc` | Escalation, strategic oversight | Magenta |

**Avatar spec:**
- 36px in header, 56px in profile, 24px in overview list
- SVG gradient circle with centered emoji
- No text in avatar (emoji is universal)
- Smooth crossfade transitions on agent change

---

*End of UI/UX Concept Document. Build from this — iterate from shipped product, not from perfection.*
