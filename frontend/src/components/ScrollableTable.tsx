import * as React from "react";

type ScrollableTableProps = {
  children: React.ReactNode;
};

export function ScrollableTable({ children }: ScrollableTableProps): JSX.Element {
  const topRef = React.useRef<HTMLDivElement | null>(null);
  const bodyRef = React.useRef<HTMLDivElement | null>(null);
  const contentRef = React.useRef<HTMLDivElement | null>(null);
  const [scrollWidth, setScrollWidth] = React.useState(0);
  const [clientWidth, setClientWidth] = React.useState(0);
  const syncing = React.useRef(false);

  React.useLayoutEffect(() => {
    const body = bodyRef.current;
    const content = contentRef.current;
    if (!body || !content) {
      return;
    }
    const update = () => {
      setScrollWidth(content.scrollWidth);
      setClientWidth(body.clientWidth);
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(body);
    observer.observe(content);
    return () => observer.disconnect();
  }, [children]);

  const syncScroll = (source: "top" | "body") => {
    if (syncing.current) {
      return;
    }
    const top = topRef.current;
    const body = bodyRef.current;
    if (!top || !body) {
      return;
    }
    syncing.current = true;
    if (source === "top") {
      body.scrollLeft = top.scrollLeft;
    } else {
      top.scrollLeft = body.scrollLeft;
    }
    requestAnimationFrame(() => {
      syncing.current = false;
    });
  };

  const showTopScroll = scrollWidth > clientWidth + 1;

  return (
    <div className="space-y-1">
      {showTopScroll ? (
        <div
          ref={topRef}
          className="data-table-scrollbar"
          onScroll={() => syncScroll("top")}
          aria-hidden="true"
        >
          <div style={{ width: scrollWidth, height: 1 }} />
        </div>
      ) : null}
      <div
        ref={bodyRef}
        className="data-table-wrap"
        onScroll={() => syncScroll("body")}
      >
        <div ref={contentRef} className="inline-block min-w-full align-top">
          {children}
        </div>
      </div>
    </div>
  );
}
