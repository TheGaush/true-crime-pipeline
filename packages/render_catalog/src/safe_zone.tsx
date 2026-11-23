/**
 * CSS containment frame for YouTube exclusion zones.
 * The package tsconfig has no `jsx` flag, so this is a React-style element tree
 * (type + props + children) rather than JSX.
 */
import { REMOTION_ROOT } from "./parser.js";

export const SAFE_ZONE_PADDING_TOP_PX = 108;
export const SAFE_ZONE_PADDING_BOTTOM_PX = 194;
export const SAFE_ZONE_EXCLUSION_WIDTH = "22%";
export const SAFE_ZONE_EXCLUSION_HEIGHT = "14%";
export const SAFE_ZONE_LABEL_MAX_LINES = 3;
export const SAFE_ZONE_LABEL_FONT_SIZE = "clamp(24px, 2.2vw, 42px)";
export const SAFE_ZONE_LABEL_LINE_HEIGHT = 1.15;
export const SAFE_ZONE_LABEL_MAX_HEIGHT = "clamp(82.8px, 7.59vw, 144.9px)";

export type CssValue = string | number;

export type SafeZoneStyle = Readonly<Record<string, CssValue>>;

export type SafeZoneChild = SafeZoneElement | string;

export type SafeZoneElement = {
  readonly type: "div";
  readonly dataset: Readonly<Record<string, string>>;
  readonly props: {
    readonly style: SafeZoneStyle;
    readonly children?: SafeZoneChild | readonly SafeZoneChild[];
  };
};

export type SafeZoneLayoutProps = {
  readonly isEndScreen: boolean;
  readonly label?: string;
  readonly children?: SafeZoneChild;
};

export type Rect = {
  readonly x: number;
  readonly y: number;
  readonly width: number;
  readonly height: number;
};

export type SafeZoneMeasurement = {
  readonly element: SafeZoneElement;
  readonly frame: Rect;
  readonly content: Rect;
  readonly exclusion: Rect;
  readonly label: Rect | null;
  readonly endScreenCard: Rect | null;
  readonly captionBar: Rect;
};

function element(
  dataset: Readonly<Record<string, string>>,
  style: SafeZoneStyle,
  children?: readonly SafeZoneChild[],
): SafeZoneElement {
  const props: SafeZoneElement["props"] = { style };
  if (children && children.length === 1) {
    const only = children[0];
    if (only !== undefined) return { type: "div", dataset, props: { style, children: only } };
  }
  if (children && children.length > 1) return { type: "div", dataset, props: { style, children } };
  return { type: "div", dataset, props };
}

function containedTypeStyle(): SafeZoneStyle {
  return {
    overflow: "hidden",
    display: "-webkit-box",
    WebkitLineClamp: SAFE_ZONE_LABEL_MAX_LINES,
    WebkitBoxOrient: "vertical",
    overflowWrap: "anywhere",
    fontSize: SAFE_ZONE_LABEL_FONT_SIZE,
    lineHeight: SAFE_ZONE_LABEL_LINE_HEIGHT,
    maxHeight: SAFE_ZONE_LABEL_MAX_HEIGHT,
  };
}

function asList(children: SafeZoneLayoutProps["children"]): readonly SafeZoneChild[] {
  if (children === undefined) return [];
  return [children];
}

function labelElement(label: string): SafeZoneElement {
  return element(
    { slot: "label" },
    {
      ...containedTypeStyle(),
      marginTop: "auto",
      width: "100%",
      minWidth: 0,
    },
    [label],
  );
}

export function SafeZoneLayout(props: SafeZoneLayoutProps): SafeZoneElement {
  const label = props.label === undefined ? null : labelElement(props.label);
  const contentChildren: SafeZoneChild[] = [...asList(props.children)];
  if (!props.isEndScreen && label) contentChildren.push(label);
  const cardChildren: SafeZoneChild[] = props.isEndScreen && label ? [label] : [];
  const layers: SafeZoneChild[] = [
    element(
      { slot: "content" },
      {
        display: "flex",
        flexDirection: "column",
        minWidth: 0,
        minHeight: 0,
        overflow: "hidden",
        width: "100%",
        height: "100%",
      },
      contentChildren,
    ),
    element(
      { exclusion: "bottom-right" },
      {
        position: "absolute",
        right: 0,
        bottom: 0,
        width: SAFE_ZONE_EXCLUSION_WIDTH,
        height: SAFE_ZONE_EXCLUSION_HEIGHT,
        overflow: "hidden",
        pointerEvents: "none",
      },
    ),
  ];
  if (props.isEndScreen) {
    layers.push(
      element(
        { mask: "end-screen-card" },
        {
          ...containedTypeStyle(),
          position: "absolute",
          left: 0,
          right: SAFE_ZONE_EXCLUSION_WIDTH,
          bottom: SAFE_ZONE_PADDING_BOTTOM_PX,
          overflow: "hidden",
        },
        cardChildren,
      ),
    );
  }
  return element(
    {
      "safe-zone": "css-contained",
      "end-screen": props.isEndScreen ? "true" : "false",
    },
    {
      boxSizing: "border-box",
      position: "relative",
      display: "grid",
      gridTemplateColumns: "minmax(0, 1fr)",
      gridTemplateRows: "minmax(0, 1fr)",
      width: REMOTION_ROOT.width,
      height: REMOTION_ROOT.height,
      paddingTop: SAFE_ZONE_PADDING_TOP_PX,
      paddingBottom: SAFE_ZONE_PADDING_BOTTOM_PX,
      paddingLeft: 0,
      paddingRight: 0,
      overflow: "hidden",
    },
    layers,
  );
}

export function resolveCssLength(value: CssValue, framePx: number): number {
  if (typeof value === "number") return value;
  const clamp = /^clamp\(([-\d.]+)px,\s*([-\d.]+)vw,\s*([-\d.]+)px\)$/.exec(value);
  if (clamp) {
    const min = Number(clamp[1]);
    const preferred = (Number(clamp[2]) / 100) * framePx;
    const max = Number(clamp[3]);
    return Math.min(max, Math.max(min, preferred));
  }
  const percent = /^([-\d.]+)%$/.exec(value);
  if (percent) return (Number(percent[1]) / 100) * framePx;
  const pixels = /^([-\d.]+)px$/.exec(value);
  if (pixels) return Number(pixels[1]);
  throw new Error(`unsupported CSS length: ${value}`);
}

function padding(style: SafeZoneStyle, side: "Top" | "Right" | "Bottom" | "Left"): number {
  const value = style[`padding${side}`];
  if (value === undefined) return 0;
  if (typeof value !== "number") throw new Error(`padding${side} must be a px number`);
  return value;
}

function findDataset(root: SafeZoneElement, key: string, expected: string): SafeZoneElement {
  const found = walkSafeZone(root).find((node) => node.dataset[key] === expected);
  if (!found) throw new Error(`missing [data-${key}=${expected}]`);
  return found;
}

export function walkSafeZone(node: SafeZoneChild, into: SafeZoneElement[] = []): SafeZoneElement[] {
  if (typeof node === "string") return into;
  into.push(node);
  const children = node.props.children;
  if (children === undefined) return into;
  const list = Array.isArray(children) ? children : [children];
  for (const child of list) walkSafeZone(child, into);
  return into;
}

function usedTextHeight(style: SafeZoneStyle, frameWidth: number, available: number): number {
  const maxHeight = style.maxHeight;
  if (maxHeight === undefined) return available;
  return Math.min(available, resolveCssLength(maxHeight, frameWidth));
}

export function measureSafeZone(props: SafeZoneLayoutProps): SafeZoneMeasurement {
  const element = SafeZoneLayout(props);
  const style = element.props.style;
  const width = style.width;
  const height = style.height;
  if (typeof width !== "number" || typeof height !== "number") {
    throw new Error("safe-zone frame width and height must be px numbers");
  }
  const padTop = padding(style, "Top");
  const padRight = padding(style, "Right");
  const padBottom = padding(style, "Bottom");
  const padLeft = padding(style, "Left");
  const frame: Rect = { x: 0, y: 0, width, height };
  const content: Rect = {
    x: padLeft,
    y: padTop,
    width: width - padLeft - padRight,
    height: height - padTop - padBottom,
  };
  const exclusionNode = findDataset(element, "exclusion", "bottom-right");
  const exclusionWidth = resolveCssLength(exclusionNode.props.style.width ?? "0px", width);
  const exclusionHeight = resolveCssLength(exclusionNode.props.style.height ?? "0px", height);
  const exclusion: Rect = {
    x: width - exclusionWidth,
    y: height - exclusionHeight,
    width: exclusionWidth,
    height: exclusionHeight,
  };
  const captionBar: Rect = { x: 0, y: height - padBottom, width, height: padBottom };
  const labelNode = walkSafeZone(element).find((node) => node.dataset.slot === "label") ?? null;
  const label = !props.isEndScreen && labelNode
    ? (() => {
        const labelHeight = usedTextHeight(labelNode.props.style, width, content.height);
        return {
          x: content.x,
          y: content.y + content.height - labelHeight,
          width: content.width,
          height: labelHeight,
        };
      })()
    : null;
  const cardNode = props.isEndScreen ? findDataset(element, "mask", "end-screen-card") : null;
  const endScreenCard = cardNode
    ? (() => {
        const cardStyle = cardNode.props.style;
        const left = typeof cardStyle.left === "number" ? cardStyle.left : 0;
        const rightInset = resolveCssLength(cardStyle.right ?? 0, width);
        const bottomInset = typeof cardStyle.bottom === "number" ? cardStyle.bottom : 0;
        const cardWidth = width - left - rightInset;
        const cardHeight = usedTextHeight(cardStyle, width, height - padTop - bottomInset);
        return {
          x: left,
          y: height - bottomInset - cardHeight,
          width: cardWidth,
          height: cardHeight,
        };
      })()
    : null;
  return { element, frame, content, exclusion, label, endScreenCard, captionBar };
}
