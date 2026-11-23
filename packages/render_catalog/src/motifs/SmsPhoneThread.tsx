/**
 * Motif 6 — SmsPhoneThread.
 *
 * Dark evidence chat inside a phone bezel. The package tsconfig has no `jsx`
 * flag (Task 001), so `<SafeZoneLayout>` is a function in this file. Task 101's
 * `safe_zone.tsx` and Task 110's `SfxRegistry.ts` are other branches. They are
 * not copied here.
 *
 * The frozen SQL catalog's sixth Remotion name is `AnimatedMapRoute`.
 * `MOTIF_REGISTRY_V1` stays the four MVP motifs. This file does not amend that
 * contract. Task 120 still owns this component as motif 6.
 *
 * A thread taller than the glass eases inside the bezel. `overflow: hidden` on
 * the bezel and the screen is the clip. `typing_tap` cues use the 48 kHz mix
 * clock, a 60 ms cooldown, and a 40 ms envelope so kept taps do not overlap.
 */

export const SMS_PHONE_THREAD_ID = "SmsPhoneThread" as const;
export const SMS_PHONE_THREAD_OWNER = "render_catalog" as const;
export const SMS_MOTIF_NUMBER = 6 as const;
export const TYPING_TAP_CUE = "typing_tap" as const;

export const FRAME_WIDTH = 1920;
export const FRAME_HEIGHT = 1080;
export const FRAME_FPS = 30;
export const SAFE_PADDING_TOP = 108;
export const SAFE_PADDING_BOTTOM = 194;
export const END_SCREEN_MASK_H = 48;
export const EXCLUSION_WIDTH = "22%";
export const EXCLUSION_HEIGHT = "14%";

export const PHONE_W = 400;
export const PHONE_H = 680;
export const BEZEL_INSET_X = 22;
export const BEZEL_INSET_TOP = 72;
export const BEZEL_INSET_BOTTOM = 40;
export const STATUS_Y = 28;
export const STATUS_H = 28;
export const HOME_W = 96;
export const HOME_H = 4;
export const HOME_FROM_BOTTOM = 22;

export const THREAD_PAD = 14;
export const BUBBLE_GAP = 12;
export const BUBBLE_PAD_X = 16;
export const BUBBLE_PAD_Y = 10;
export const BUBBLE_MAX_W = 268;
export const CHAR_PX = 11;
export const LINE_H = 26;
export const MAX_LINES = 4;
export const TYPING_W = 84;
export const TYPING_H = 40;
export const SCROLL_EASE_FRAMES = 8;
export const DEFAULT_TYPING_FRAMES = 12;
export const TAP_STRIDE_FRAMES = 3;

export const MIX_SAMPLE_RATE_HZ = 48_000;
export const SAMPLES_PER_FRAME = MIX_SAMPLE_RATE_HZ / FRAME_FPS;
export const COOLDOWN_MS = 60;
export const COOLDOWN_SAMPLES = (COOLDOWN_MS * MIX_SAMPLE_RATE_HZ) / 1_000;
export const TYPING_TAP_DURATION_MS = 40;
export const TYPING_TAP_DURATION_SAMPLES = TYPING_TAP_DURATION_MS * (MIX_SAMPLE_RATE_HZ / 1_000);
export const BURST_CUE_LIMIT = 12;
export const BURST_WINDOW_SAMPLES = MIX_SAMPLE_RATE_HZ;
export const TYPING_TAP_DBTP = -12;
export const GAIN_UNIT_SCALE = 1_000_000_000;
export const TRUE_PEAK_CEILING_DBTP = -1;

export const PAPER_BG = "#F4F1EA";
export const BEZEL_BG = "#14161A";
export const SCREEN_BG = "#0C0E12";
export const BUBBLE_INBOUND_BG = "#242B33";
export const BUBBLE_OUTBOUND_BG = "#3A342C";
export const BUBBLE_TEXT = "#E6E1D6";
export const HIGHLIGHT_BORDER = "#C4A574";
export const IDLE_BORDER = "#2A3036";
export const STATUS_COLOR = "#A8B0B8";
export const HOME_BG = "#3A3F46";
export const TYPING_BG = "#1C2228";
export const TYPING_DOT = "#9AA3AD";
export const STATUS_LABEL = "EVIDENCE SMS";

const ID_PATTERN = /^[A-Za-z0-9_-]{1,128}$/;
const MAX_BODY = 400;

export const TYPING_TAP_GAIN_UNITS = linearGainUnits(TYPING_TAP_DBTP);
export const TRUE_PEAK_CEILING_UNITS = linearGainUnits(TRUE_PEAK_CEILING_DBTP);

export const SMS_PARTIES = ["inbound", "outbound"] as const;
export type SmsParty = (typeof SMS_PARTIES)[number];

export type CssValue = string | number;

export type Rect = {
  readonly x: number;
  readonly y: number;
  readonly width: number;
  readonly height: number;
};

export type SmsChild = SmsNode | string;

export type SmsNode = {
  readonly type: "div";
  readonly dataset: Readonly<Record<string, string>>;
  readonly props: {
    readonly style: Readonly<Record<string, CssValue>>;
    readonly children?: SmsChild | readonly SmsChild[];
  };
};

export type SmsMessage = {
  readonly message_id: string;
  readonly fact_id: string;
  readonly party: SmsParty;
  readonly body: string;
  readonly appear_frame: number;
  readonly typing_frames?: number;
};

export type SmsPhoneThreadProps = {
  readonly messages: readonly SmsMessage[];
  readonly frame: number;
  readonly sceneId?: string;
  readonly highlightMessageId?: string;
  readonly isEndScreen?: boolean;
};

export type TypingTapCue = {
  readonly cue_id: string;
  readonly cue: typeof TYPING_TAP_CUE;
  readonly scene_id: string;
  readonly message_id: string;
  readonly start_frame: number;
  readonly start_sample: number;
  readonly sample_rate_hz: typeof MIX_SAMPLE_RATE_HZ;
  readonly offset_ms: number;
  readonly duration_samples: typeof TYPING_TAP_DURATION_SAMPLES;
  readonly cooldown_ms: typeof COOLDOWN_MS;
  readonly gain_units: number;
  readonly gain_unit_scale: typeof GAIN_UNIT_SCALE;
  readonly peak_dbtp: number;
  readonly burst: boolean;
  readonly tapered: boolean;
};

export type SuppressedTypingTap = {
  readonly cue: typeof TYPING_TAP_CUE;
  readonly message_id: string;
  readonly start_frame: number;
  readonly start_sample: number;
  readonly reason: "cooldown";
};

export type PlacedRow = {
  readonly box: Rect;
  readonly page: Rect;
  readonly visible: Rect | null;
  readonly clipped: boolean;
};

export type PlacedBubble = PlacedRow & {
  readonly message_id: string;
  readonly fact_id: string;
  readonly party: SmsParty;
  readonly body: string;
  readonly display: string;
  readonly truncated: boolean;
  readonly appear_frame: number;
  readonly highlight: boolean;
};

export type PlacedTyping = PlacedRow & {
  readonly message_id: string;
  readonly party: SmsParty;
  readonly window_start: number;
  readonly window_end: number;
};

export type SmsPhoneThreadLayout = {
  readonly motif: typeof SMS_PHONE_THREAD_ID;
  readonly owner: typeof SMS_PHONE_THREAD_OWNER;
  readonly motifNumber: typeof SMS_MOTIF_NUMBER;
  readonly frame: number;
  readonly sceneId: string;
  readonly isEndScreen: boolean;
  readonly content: Rect;
  readonly exclusion: Rect;
  readonly captionBar: Rect;
  readonly endScreenMask: Rect | null;
  readonly phone: Rect;
  readonly screen: Rect;
  readonly status: Rect;
  readonly home: Rect;
  readonly scrollOffset: number;
  readonly scrollTarget: number;
  readonly overflows: boolean;
  readonly contentHeight: number;
  readonly typing: PlacedTyping | null;
  readonly bubbles: readonly PlacedBubble[];
  readonly cues: readonly TypingTapCue[];
  readonly cuesStarted: readonly TypingTapCue[];
  readonly suppressed: readonly SuppressedTypingTap[];
  readonly highlightMessageId: string | null;
};

type NormalizedMessage = {
  readonly message_id: string;
  readonly fact_id: string;
  readonly party: SmsParty;
  readonly body: string;
  readonly appear_frame: number;
  readonly typing_frames: number;
};

type Prepared = {
  readonly messages: readonly NormalizedMessage[];
  readonly sceneId: string;
  readonly highlightMessageId: string | null;
  readonly isEndScreen: boolean;
  readonly frame: number;
  readonly cues: readonly TypingTapCue[];
  readonly suppressed: readonly SuppressedTypingTap[];
};

type LocalItem = {
  readonly kind: "bubble" | "typing";
  readonly message: NormalizedMessage;
  readonly box: Rect;
  readonly display: string;
  readonly truncated: boolean;
};

type ScrollAnchor = {
  readonly frame: number;
  readonly target: number;
};

export class SmsPhoneThreadError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SmsPhoneThreadError";
  }
}

export function linearGainUnits(dbtp: number): number {
  if (!Number.isFinite(dbtp) || dbtp > TRUE_PEAK_CEILING_DBTP) {
    throw new SmsPhoneThreadError(`nominal peak ${dbtp} dBTP exceeds ${TRUE_PEAK_CEILING_DBTP} dBTP`);
  }
  return Math.floor(10 ** (dbtp / 20) * GAIN_UNIT_SCALE + 1e-6);
}

export function contentRect(): Rect {
  return {
    x: 0,
    y: SAFE_PADDING_TOP,
    width: FRAME_WIDTH,
    height: FRAME_HEIGHT - SAFE_PADDING_TOP - SAFE_PADDING_BOTTOM,
  };
}

export function exclusionRect(): Rect {
  const width = FRAME_WIDTH * 0.22;
  const height = FRAME_HEIGHT * 0.14;
  return {
    x: FRAME_WIDTH - width,
    y: FRAME_HEIGHT - height,
    width,
    height,
  };
}

export function captionBarRect(): Rect {
  return {
    x: 0,
    y: FRAME_HEIGHT - SAFE_PADDING_BOTTOM,
    width: FRAME_WIDTH,
    height: SAFE_PADDING_BOTTOM,
  };
}

export function endScreenMaskRect(): Rect {
  const exclusion = exclusionRect();
  const caption = captionBarRect();
  return {
    x: 0,
    y: caption.y - END_SCREEN_MASK_H,
    width: exclusion.x,
    height: END_SCREEN_MASK_H,
  };
}

export function rectsOverlap(a: Rect, b: Rect): boolean {
  return a.x < b.x + b.width && a.x + a.width > b.x && a.y < b.y + b.height && a.y + a.height > b.y;
}

export function rectInside(inner: Rect, outer: Rect): boolean {
  return (
    inner.x >= outer.x &&
    inner.y >= outer.y &&
    inner.x + inner.width <= outer.x + outer.width &&
    inner.y + inner.height <= outer.y + outer.height
  );
}

export function walkSms(node: SmsChild, into: SmsNode[] = []): SmsNode[] {
  if (typeof node === "string") return into;
  into.push(node);
  const children = node.props.children;
  if (children === undefined) return into;
  const list = Array.isArray(children) ? children : [children];
  for (const child of list) walkSms(child, into);
  return into;
}

export function textColumns(): number {
  return Math.floor((BUBBLE_MAX_W - BUBBLE_PAD_X * 2) / CHAR_PX);
}

export function layoutSmsPhoneThread(props: SmsPhoneThreadProps): SmsPhoneThreadLayout {
  const prepared = prepare(props);
  const chrome = placePhone(prepared.isEndScreen);
  const anchors = scrollAnchors(prepared.messages, chrome.screen.height);
  const scrollTarget = targetAt(anchors, prepared.frame);
  const scrollOffset = scrollOffsetAt(prepared.frame, anchors);
  const placed = layoutItems(prepared.messages, prepared.frame, chrome.screen.width);
  const bubbles = placed.items
    .filter((item) => item.kind === "bubble")
    .map((item) => placeBubble(item, chrome.screen, scrollOffset, prepared.highlightMessageId));
  const typingItem = placed.items.find((item) => item.kind === "typing") ?? null;
  const typing = typingItem ? placeTyping(typingItem, chrome.screen, scrollOffset) : null;
  const layout: SmsPhoneThreadLayout = {
    motif: SMS_PHONE_THREAD_ID,
    owner: SMS_PHONE_THREAD_OWNER,
    motifNumber: SMS_MOTIF_NUMBER,
    frame: prepared.frame,
    sceneId: prepared.sceneId,
    isEndScreen: prepared.isEndScreen,
    content: contentRect(),
    exclusion: exclusionRect(),
    captionBar: captionBarRect(),
    endScreenMask: prepared.isEndScreen ? endScreenMaskRect() : null,
    phone: chrome.phone,
    screen: chrome.screen,
    status: chrome.status,
    home: chrome.home,
    scrollOffset,
    scrollTarget,
    overflows: placed.contentHeight > chrome.screen.height,
    contentHeight: placed.contentHeight,
    typing,
    bubbles,
    cues: prepared.cues,
    cuesStarted: prepared.cues.filter((cue) => cue.start_frame <= prepared.frame),
    suppressed: prepared.suppressed,
    highlightMessageId: prepared.highlightMessageId,
  };
  assertBezelClippedScroll(layout);
  return layout;
}

export function assertBezelClippedScroll(layout: SmsPhoneThreadLayout): void {
  if (!rectInside(layout.phone, layout.content)) fail("phone leaves the safe zone");
  if (!strictlyInside(layout.screen, layout.phone)) fail("screen leaves the bezel");
  if (rectsOverlap(layout.phone, layout.captionBar)) fail("phone enters the caption bar");
  if (rectsOverlap(layout.phone, layout.exclusion)) fail("phone enters the exclusion box");
  if (layout.endScreenMask && rectsOverlap(layout.phone, layout.endScreenMask)) {
    fail("phone enters the end-screen mask");
  }
  if (!rectInside(layout.status, layout.phone) || rectsOverlap(layout.status, layout.screen)) {
    fail("status leaves the bezel chrome");
  }
  if (!rectInside(layout.home, layout.phone) || rectsOverlap(layout.home, layout.screen)) {
    fail("home bar leaves the bezel chrome");
  }
  if (layout.scrollOffset < 0 || layout.scrollOffset > layout.scrollTarget) {
    fail("scroll leaves the bezel");
  }
  if (layout.overflows !== layout.contentHeight > layout.screen.height) fail("overflow flag disagrees with the screen");
  if (layout.overflows && layout.scrollTarget <= 0) fail("overflow did not scroll");
  if (!layout.overflows && layout.scrollTarget !== 0) fail("short thread scrolled");
  for (const bubble of layout.bubbles) assertRow(layout, bubble.box, bubble.page, bubble.visible, bubble.message_id);
  if (layout.typing) assertRow(layout, layout.typing.box, layout.typing.page, layout.typing.visible, "typing");
}

export function SmsPhoneThread(props: SmsPhoneThreadProps): SmsNode {
  const layout = layoutSmsPhoneThread(props);
  const origin = layout.content;
  const threadChildren: SmsChild[] = [];
  if (layout.typing) {
    threadChildren.push(
      element(
        {
          slot: "typing",
          "message-id": layout.typing.message_id,
          party: layout.typing.party,
          cue: TYPING_TAP_CUE,
          "window-start": String(layout.typing.window_start),
          "window-end": String(layout.typing.window_end),
        },
        {
          position: "absolute",
          left: layout.typing.box.x,
          top: layout.typing.box.y,
          width: layout.typing.box.width,
          height: layout.typing.box.height,
          boxSizing: "border-box",
          overflow: "hidden",
          borderRadius: 18,
          background: TYPING_BG,
          color: TYPING_DOT,
          fontSize: 22,
          lineHeight: `${TYPING_H}px`,
          textAlign: "center",
        },
        ["● ● ●"],
      ),
    );
  }
  for (const bubble of layout.bubbles) {
    threadChildren.push(
      element(
        {
          slot: "bubble",
          "message-id": bubble.message_id,
          "fact-id": bubble.fact_id,
          party: bubble.party,
          highlight: bubble.highlight ? "true" : "false",
          truncated: bubble.truncated ? "true" : "false",
          body: bubble.body,
        },
        {
          position: "absolute",
          left: bubble.box.x,
          top: bubble.box.y,
          width: bubble.box.width,
          height: bubble.box.height,
          boxSizing: "border-box",
          overflow: "hidden",
          borderRadius: 18,
          padding: `${BUBBLE_PAD_Y}px ${BUBBLE_PAD_X}px`,
          background: bubble.party === "inbound" ? BUBBLE_INBOUND_BG : BUBBLE_OUTBOUND_BG,
          color: BUBBLE_TEXT,
          border: `2px solid ${bubble.highlight ? HIGHLIGHT_BORDER : IDLE_BORDER}`,
          fontSize: 22,
          lineHeight: `${LINE_H}px`,
          whiteSpace: "pre",
        },
        [bubble.display],
      ),
    );
  }
  const cueNodes = layout.cues.map((cue) =>
    element(
      {
        slot: "typing-tap",
        cue: TYPING_TAP_CUE,
        "message-id": cue.message_id,
        "start-frame": String(cue.start_frame),
        "start-sample": String(cue.start_sample),
        tapered: cue.tapered ? "true" : "false",
        burst: cue.burst ? "true" : "false",
      },
      {
        position: "absolute",
        left: 0,
        top: 0,
        width: 0,
        height: 0,
        overflow: "hidden",
      },
    ),
  );
  const phoneChildren: SmsChild[] = [
    element(
      { slot: "status" },
      {
        position: "absolute",
        left: layout.status.x - layout.phone.x,
        top: layout.status.y - layout.phone.y,
        width: layout.status.width,
        height: layout.status.height,
        overflow: "hidden",
        color: STATUS_COLOR,
        fontSize: 18,
        lineHeight: `${STATUS_H}px`,
        textAlign: "center",
      },
      [STATUS_LABEL],
    ),
    element(
      { slot: "screen", scroll: String(layout.scrollOffset) },
      {
        position: "absolute",
        left: layout.screen.x - layout.phone.x,
        top: layout.screen.y - layout.phone.y,
        width: layout.screen.width,
        height: layout.screen.height,
        overflow: "hidden",
        background: SCREEN_BG,
        borderRadius: 24,
      },
      [
        element(
          { slot: "thread" },
          {
            position: "absolute",
            left: 0,
            top: layout.scrollOffset === 0 ? 0 : -layout.scrollOffset,
            width: layout.screen.width,
            height: layout.contentHeight,
            overflow: "hidden",
          },
          threadChildren,
        ),
      ],
    ),
    element(
      { slot: "home-bar" },
      {
        position: "absolute",
        left: layout.home.x - layout.phone.x,
        top: layout.home.y - layout.phone.y,
        width: layout.home.width,
        height: layout.home.height,
        overflow: "hidden",
        borderRadius: 2,
        background: HOME_BG,
      },
    ),
    ...cueNodes,
  ];
  const layers: SmsChild[] = [
    element(
      { slot: "content" },
      {
        position: "relative",
        display: "flex",
        flexDirection: "column",
        minWidth: 0,
        minHeight: 0,
        overflow: "hidden",
        width: "100%",
        height: "100%",
      },
      [
        element(
          {
            slot: "bezel",
            motif: SMS_PHONE_THREAD_ID,
            "motif-number": String(SMS_MOTIF_NUMBER),
          },
          {
            position: "absolute",
            left: layout.phone.x - origin.x,
            top: layout.phone.y - origin.y,
            width: layout.phone.width,
            height: layout.phone.height,
            boxSizing: "border-box",
            overflow: "hidden",
            borderRadius: 36,
            background: BEZEL_BG,
          },
          phoneChildren,
        ),
      ],
    ),
    element(
      { exclusion: "bottom-right" },
      {
        position: "absolute",
        right: 0,
        bottom: 0,
        width: EXCLUSION_WIDTH,
        height: EXCLUSION_HEIGHT,
        overflow: "hidden",
        pointerEvents: "none",
      },
    ),
  ];
  if (layout.endScreenMask) {
    layers.push(
      element(
        { mask: "end-screen-card" },
        {
          position: "absolute",
          left: layout.endScreenMask.x,
          top: layout.endScreenMask.y,
          width: layout.endScreenMask.width,
          height: layout.endScreenMask.height,
          overflow: "hidden",
          pointerEvents: "none",
        },
      ),
    );
  }
  return SafeZoneLayout({ isEndScreen: layout.isEndScreen, children: layers });
}

function SafeZoneLayout(props: { readonly isEndScreen: boolean; readonly children: readonly SmsChild[] }): SmsNode {
  return element(
    {
      "safe-zone": "css-contained",
      motif: SMS_PHONE_THREAD_ID,
      owner: SMS_PHONE_THREAD_OWNER,
      "motif-number": String(SMS_MOTIF_NUMBER),
      "end-screen": props.isEndScreen ? "true" : "false",
    },
    {
      boxSizing: "border-box",
      position: "relative",
      display: "grid",
      gridTemplateColumns: "minmax(0, 1fr)",
      gridTemplateRows: "minmax(0, 1fr)",
      width: FRAME_WIDTH,
      height: FRAME_HEIGHT,
      paddingTop: SAFE_PADDING_TOP,
      paddingBottom: SAFE_PADDING_BOTTOM,
      paddingLeft: 0,
      paddingRight: 0,
      overflow: "hidden",
      background: PAPER_BG,
    },
    props.children,
  );
}

function prepare(props: SmsPhoneThreadProps): Prepared {
  if (props === null || typeof props !== "object") fail("sms thread props must be an object");
  if (!Number.isInteger(props.frame) || props.frame < 0) fail("frame must be a non-negative integer");
  if (!Array.isArray(props.messages) || props.messages.length === 0) fail("messages must be a non-empty list");
  const sceneId = props.sceneId === undefined ? "sms_phone_thread" : readId(props.sceneId, "scene_id");
  const isEndScreen = props.isEndScreen === undefined ? false : props.isEndScreen;
  if (typeof isEndScreen !== "boolean") fail("isEndScreen must be a boolean");
  const messages = props.messages.map((message, index) => readMessage(message, index));
  const seen = new Set<string>();
  for (const message of messages) {
    if (seen.has(message.message_id)) fail(`duplicate message_id: ${message.message_id}`);
    seen.add(message.message_id);
  }
  for (let index = 1; index < messages.length; index += 1) {
    const message = messages[index];
    const previous = messages[index - 1];
    if (!message || !previous) fail("messages must be a non-empty list");
    if (message.appear_frame <= previous.appear_frame) fail("appear_frame must increase");
    if (message.appear_frame - message.typing_frames < previous.appear_frame) {
      fail("typing window overlaps the previous message");
    }
  }
  let highlightMessageId: string | null = null;
  if (props.highlightMessageId !== undefined) {
    highlightMessageId = readId(props.highlightMessageId, "highlight");
    if (!seen.has(highlightMessageId)) fail(`highlight message is not in the thread: ${highlightMessageId}`);
  }
  const schedule = scheduleTaps(messages, sceneId);
  return {
    messages,
    sceneId,
    highlightMessageId,
    isEndScreen,
    frame: props.frame,
    cues: schedule.cues,
    suppressed: schedule.suppressed,
  };
}

function readMessage(value: SmsMessage, index: number): NormalizedMessage {
  if (value === null || typeof value !== "object") fail(`messages[${index}] must be an object`);
  const messageId = readId(value.message_id, "message_id");
  const factId = readId(value.fact_id, "fact_id");
  if (typeof value.party !== "string" || !isParty(value.party)) fail(`party must be inbound or outbound at ${messageId}`);
  if (typeof value.body !== "string" || value.body.trim().length === 0 || value.body.trim().length > MAX_BODY) {
    fail(`body must be 1–${MAX_BODY} characters at ${messageId}`);
  }
  if (!Number.isInteger(value.appear_frame) || value.appear_frame < 0) {
    fail(`appear_frame must be a non-negative integer at ${messageId}`);
  }
  const typing = value.typing_frames === undefined ? DEFAULT_TYPING_FRAMES : value.typing_frames;
  if (!Number.isInteger(typing) || typing < 0 || typing > value.appear_frame) {
    fail(`typing_frames must start at frame 0 or later at ${messageId}`);
  }
  return {
    message_id: messageId,
    fact_id: factId,
    party: value.party,
    body: value.body.trim(),
    appear_frame: value.appear_frame,
    typing_frames: typing,
  };
}

function readId(value: unknown, label: string): string {
  if (typeof value !== "string" || !ID_PATTERN.test(value)) fail(`${label} must match ${ID_PATTERN}`);
  return value;
}

function isParty(value: string): value is SmsParty {
  return value === "inbound" || value === "outbound";
}

function scheduleTaps(
  messages: readonly NormalizedMessage[],
  sceneId: string,
): { cues: TypingTapCue[]; suppressed: SuppressedTypingTap[] } {
  if (TYPING_TAP_DURATION_SAMPLES >= COOLDOWN_SAMPLES) {
    fail("typing_tap envelope must be shorter than the 60 ms cooldown");
  }
  const planned: { messageId: string; frame: number; sample: number }[] = [];
  for (const message of messages) {
    if (message.typing_frames <= 0) continue;
    const start = message.appear_frame - message.typing_frames;
    for (let frame = start; frame < message.appear_frame; frame += TAP_STRIDE_FRAMES) {
      planned.push({ messageId: message.message_id, frame, sample: frame * SAMPLES_PER_FRAME });
    }
  }
  planned.sort((a, b) => a.sample - b.sample || (a.messageId < b.messageId ? -1 : a.messageId > b.messageId ? 1 : 0));
  const kept: typeof planned = [];
  const suppressed: SuppressedTypingTap[] = [];
  let lastSample: number | null = null;
  for (const tap of planned) {
    if (lastSample !== null && tap.sample - lastSample < COOLDOWN_SAMPLES) {
      suppressed.push({
        cue: TYPING_TAP_CUE,
        message_id: tap.messageId,
        start_frame: tap.frame,
        start_sample: tap.sample,
        reason: "cooldown",
      });
      continue;
    }
    kept.push(tap);
    lastSample = tap.sample;
  }
  const samples = kept.map((tap) => tap.sample);
  const burst = markBursts(samples);
  let burstIndex = 0;
  const cues = kept.map((tap, index) => {
    const inBurst = burst[index] === true;
    const shift = inBurst ? burstIndex : 0;
    if (inBurst) burstIndex += 1;
    else burstIndex = 0;
    const gain = shiftGain(TYPING_TAP_GAIN_UNITS, shift);
    return toCue(sceneId, tap.messageId, tap.frame, tap.sample, gain, inBurst);
  });
  return { cues, suppressed };
}

function markBursts(samples: readonly number[]): boolean[] {
  const burst = samples.map(() => false);
  let right = 0;
  for (let left = 0; left < samples.length; left += 1) {
    const origin = samples[left];
    if (origin === undefined) continue;
    if (right < left) right = left;
    while (right + 1 < samples.length) {
      const next = samples[right + 1];
      if (next === undefined || next - origin >= BURST_WINDOW_SAMPLES) break;
      right += 1;
    }
    if (right - left + 1 > BURST_CUE_LIMIT) {
      for (let index = left; index <= right; index += 1) burst[index] = true;
    }
  }
  return burst;
}

function shiftGain(units: number, index: number): number {
  if (index <= 0) return units;
  if (index >= 53) return 0;
  return Number(BigInt(units) >> BigInt(index));
}

function toCue(
  sceneId: string,
  messageId: string,
  frame: number,
  sample: number,
  gain: number,
  burst: boolean,
): TypingTapCue {
  if (gain > TRUE_PEAK_CEILING_UNITS) fail("typing_tap peak exceeds -1.0 dBTP");
  return {
    cue_id: `${sceneId}:${TYPING_TAP_CUE}:${messageId}:${sample}`,
    cue: TYPING_TAP_CUE,
    scene_id: sceneId,
    message_id: messageId,
    start_frame: frame,
    start_sample: sample,
    sample_rate_hz: MIX_SAMPLE_RATE_HZ,
    offset_ms: sample / (MIX_SAMPLE_RATE_HZ / 1_000),
    duration_samples: TYPING_TAP_DURATION_SAMPLES,
    cooldown_ms: COOLDOWN_MS,
    gain_units: gain,
    gain_unit_scale: GAIN_UNIT_SCALE,
    peak_dbtp: gain === TYPING_TAP_GAIN_UNITS ? TYPING_TAP_DBTP : roundedDbtp(gain),
    burst,
    tapered: gain !== TYPING_TAP_GAIN_UNITS,
  };
}

function roundedDbtp(units: number): number {
  if (units <= 0) return TRUE_PEAK_CEILING_DBTP;
  return Math.round(20 * Math.log10(units / GAIN_UNIT_SCALE) * 1000) / 1000;
}

function placePhone(isEndScreen: boolean): { phone: Rect; screen: Rect; status: Rect; home: Rect } {
  const content = contentRect();
  const mask = isEndScreen ? endScreenMaskRect() : null;
  const usableBottom = mask ? mask.y : content.y + content.height;
  const usableHeight = usableBottom - content.y;
  if (usableHeight < PHONE_H || content.width < PHONE_W) fail("phone does not fit the safe zone");
  const phone: Rect = {
    x: content.x + Math.floor((content.width - PHONE_W) / 2),
    y: content.y + Math.floor((usableHeight - PHONE_H) / 2),
    width: PHONE_W,
    height: PHONE_H,
  };
  const screen: Rect = {
    x: phone.x + BEZEL_INSET_X,
    y: phone.y + BEZEL_INSET_TOP,
    width: PHONE_W - BEZEL_INSET_X * 2,
    height: PHONE_H - BEZEL_INSET_TOP - BEZEL_INSET_BOTTOM,
  };
  const status: Rect = {
    x: phone.x + BEZEL_INSET_X,
    y: phone.y + STATUS_Y,
    width: PHONE_W - BEZEL_INSET_X * 2,
    height: STATUS_H,
  };
  const home: Rect = {
    x: phone.x + Math.floor((PHONE_W - HOME_W) / 2),
    y: phone.y + PHONE_H - HOME_FROM_BOTTOM - HOME_H,
    width: HOME_W,
    height: HOME_H,
  };
  if (status.y + status.height > screen.y) fail("status covers the screen");
  if (home.y < screen.y + screen.height) fail("home bar covers the screen");
  return { phone, screen, status, home };
}

function layoutItems(
  messages: readonly NormalizedMessage[],
  frame: number,
  screenWidth: number,
): { items: LocalItem[]; contentHeight: number } {
  const items: LocalItem[] = [];
  let y = THREAD_PAD;
  for (const message of messages) {
    const start = message.appear_frame - message.typing_frames;
    if (message.typing_frames > 0 && frame >= start && frame < message.appear_frame) {
      items.push({
        kind: "typing",
        message,
        box: placeRow(message.party, y, TYPING_W, TYPING_H, screenWidth),
        display: "● ● ●",
        truncated: false,
      });
      y += TYPING_H + BUBBLE_GAP;
    }
    if (frame >= message.appear_frame) {
      const wrapped = wrapBody(message.body);
      const width = bubbleWidth(wrapped.lines);
      const height = BUBBLE_PAD_Y * 2 + wrapped.lines.length * LINE_H;
      items.push({
        kind: "bubble",
        message,
        box: placeRow(message.party, y, width, height, screenWidth),
        display: wrapped.lines.join("\n"),
        truncated: wrapped.truncated,
      });
      y += height + BUBBLE_GAP;
    }
  }
  const contentHeight = items.length === 0 ? THREAD_PAD * 2 : y - BUBBLE_GAP + THREAD_PAD;
  return { items, contentHeight };
}

function placeRow(party: SmsParty, y: number, width: number, height: number, screenWidth: number): Rect {
  const x = party === "inbound" ? THREAD_PAD : screenWidth - THREAD_PAD - width;
  if (x < THREAD_PAD || x + width > screenWidth - THREAD_PAD) fail("bubble does not fit the screen");
  return { x, y, width, height };
}

function bubbleWidth(lines: readonly string[]): number {
  const widest = lines.reduce((max, line) => Math.max(max, line.length * CHAR_PX), 0);
  return Math.min(BUBBLE_MAX_W, widest + BUBBLE_PAD_X * 2);
}

function wrapBody(body: string): { lines: string[]; truncated: boolean } {
  const columns = textColumns();
  const words = body.trim().split(/\s+/).filter((word) => word.length > 0);
  const tokens: string[] = [];
  for (const word of words) {
    if (word.length <= columns) {
      tokens.push(word);
      continue;
    }
    for (let index = 0; index < word.length; index += columns) tokens.push(word.slice(index, index + columns));
  }
  const lines: string[] = [];
  let current = "";
  let used = 0;
  for (; used < tokens.length; used += 1) {
    const token = tokens[used] ?? "";
    const next = current.length === 0 ? token : `${current} ${token}`;
    if (next.length <= columns) {
      current = next;
      continue;
    }
    if (lines.length + 1 === MAX_LINES) break;
    if (current.length > 0) lines.push(current);
    current = token;
  }
  if (used < tokens.length) {
    const room = Math.max(1, columns - 1);
    const base = current.length > 0 ? current : (lines[lines.length - 1] ?? "");
    const ellipsis = `${base.slice(0, room).trimEnd()}…`;
    if (current.length > 0 || lines.length === 0) lines.push(ellipsis);
    else lines[lines.length - 1] = ellipsis;
    return { lines: lines.slice(0, MAX_LINES), truncated: true };
  }
  if (current.length > 0) lines.push(current);
  return { lines, truncated: false };
}

function scrollAnchors(messages: readonly NormalizedMessage[], screenHeight: number): ScrollAnchor[] {
  const frames = new Set<number>([0]);
  for (const message of messages) {
    if (message.typing_frames > 0) frames.add(message.appear_frame - message.typing_frames);
    frames.add(message.appear_frame);
  }
  return [...frames]
    .sort((a, b) => a - b)
    .map((frame) => ({
      frame,
      target: Math.max(0, layoutItems(messages, frame, PHONE_W - BEZEL_INSET_X * 2).contentHeight - screenHeight),
    }));
}

function targetAt(anchors: readonly ScrollAnchor[], frame: number): number {
  let target = 0;
  for (const anchor of anchors) {
    if (anchor.frame > frame) break;
    target = anchor.target;
  }
  return target;
}

function scrollOffsetAt(frame: number, anchors: readonly ScrollAnchor[]): number {
  let originValue = 0;
  let originFrame = 0;
  let index = 0;
  for (let cursor = 1; cursor < anchors.length; cursor += 1) {
    const anchor = anchors[cursor];
    const previous = anchors[cursor - 1];
    if (!anchor || !previous || anchor.frame > frame) break;
    originValue = eased(originValue, previous.target, anchor.frame - originFrame);
    originFrame = anchor.frame;
    index = cursor;
  }
  const latest = anchors[index];
  if (!latest) return 0;
  return eased(originValue, latest.target, frame - originFrame);
}

function eased(from: number, to: number, elapsed: number): number {
  if (elapsed <= 0) return from;
  const t = Math.min(1, elapsed / SCROLL_EASE_FRAMES);
  const curved = t * t * (3 - 2 * t);
  return Math.round(from + (to - from) * curved);
}

function placeBubble(item: LocalItem, screen: Rect, scroll: number, highlightId: string | null): PlacedBubble {
  const page = toPage(screen, scroll, item.box);
  const visible = intersection(page, screen);
  return {
    message_id: item.message.message_id,
    fact_id: item.message.fact_id,
    party: item.message.party,
    body: item.message.body,
    display: item.display,
    truncated: item.truncated,
    appear_frame: item.message.appear_frame,
    highlight: highlightId !== null && item.message.message_id === highlightId,
    box: item.box,
    page,
    visible,
    clipped: !sameRect(visible, page),
  };
}

function placeTyping(item: LocalItem, screen: Rect, scroll: number): PlacedTyping {
  const page = toPage(screen, scroll, item.box);
  const visible = intersection(page, screen);
  return {
    message_id: item.message.message_id,
    party: item.message.party,
    window_start: item.message.appear_frame - item.message.typing_frames,
    window_end: item.message.appear_frame,
    box: item.box,
    page,
    visible,
    clipped: !sameRect(visible, page),
  };
}

function toPage(screen: Rect, scroll: number, local: Rect): Rect {
  return {
    x: screen.x + local.x,
    y: screen.y + local.y - scroll,
    width: local.width,
    height: local.height,
  };
}

function intersection(a: Rect, b: Rect): Rect | null {
  const x = Math.max(a.x, b.x);
  const y = Math.max(a.y, b.y);
  const right = Math.min(a.x + a.width, b.x + b.width);
  const bottom = Math.min(a.y + a.height, b.y + b.height);
  if (right <= x || bottom <= y) return null;
  return { x, y, width: right - x, height: bottom - y };
}

function sameRect(visible: Rect | null, page: Rect): boolean {
  return (
    visible !== null &&
    visible.x === page.x &&
    visible.y === page.y &&
    visible.width === page.width &&
    visible.height === page.height
  );
}

function assertRow(layout: SmsPhoneThreadLayout, box: Rect, page: Rect, visible: Rect | null, label: string): void {
  if (box.x < 0 || box.width <= 0 || box.height <= 0 || box.x + box.width > layout.screen.width) {
    fail(`${label} is wider than the screen`);
  }
  if (page.x !== layout.screen.x + box.x || page.y !== layout.screen.y + box.y - layout.scrollOffset) {
    fail(`${label} scroll does not match the bezel`);
  }
  if (visible && !rectInside(visible, layout.screen)) fail(`${label} paints outside the bezel`);
  const fully = sameRect(visible, page);
  if (fully && !rectInside(page, layout.screen)) fail(`${label} is marked visible outside the screen`);
}

function strictlyInside(inner: Rect, outer: Rect): boolean {
  return (
    inner.x > outer.x &&
    inner.y > outer.y &&
    inner.x + inner.width < outer.x + outer.width &&
    inner.y + inner.height < outer.y + outer.height
  );
}

function element(
  dataset: Readonly<Record<string, string>>,
  style: Readonly<Record<string, CssValue>>,
  children?: readonly SmsChild[],
): SmsNode {
  if (children !== undefined && children.length > 0) {
    const only = children.length === 1 ? children[0] : children;
    if (only !== undefined) return { type: "div", dataset, props: { style, children: only } };
  }
  return { type: "div", dataset, props: { style } };
}

function fail(message: string): never {
  throw new SmsPhoneThreadError(message);
}
