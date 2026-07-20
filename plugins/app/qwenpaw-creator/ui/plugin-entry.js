(function () {
  const pluginId = "qwenpaw-creator";
  const host = window.QwenPaw && window.QwenPaw.host;
  const React = host && host.React;
  const slot = window.QwenPaw && window.QwenPaw.slot;
  if (!window.QwenPaw || !React || !host.getApiUrl || !slot?.replace) {
    console.warn("[qwenpaw-creator] QwenPaw Creator slot API is unavailable.");
    return;
  }

  const CREATOR_BG_COLOR = "#f9f8f4";
  const CREATOR_BUILD_ID = "__CREATOR_BUILD_ID__";
  const NAVIGATION_MESSAGE = "qwenpaw-creator:navigation";
  const RESTORE_ROUTE_MESSAGE = "qwenpaw-creator:restore-route";

  function normalizeCreatorRoute(path) {
    if (
      typeof path !== "string" ||
      !path.startsWith("/") ||
      path.startsWith("//") ||
      path.includes("#")
    ) {
      return null;
    }
    const parsed = new URL(path, "http://qwenpaw-creator.local");
    return `${parsed.pathname}${parsed.search}`;
  }

  function creatorRouteFromHost() {
    const route = window.location.hash.slice(1);
    return normalizeCreatorRoute(route || "/") || "/";
  }

  function hostUrlForCreatorRoute(path) {
    const route = normalizeCreatorRoute(path);
    if (!route) return null;
    return `${window.location.pathname}${window.location.search}#${route}`;
  }

  function CreatorFrame() {
    const frameRef = React.useRef(null);
    const initialSrcRef = React.useRef(null);

    if (!initialSrcRef.current) {
      const appUrl = host.getApiUrl(
        "/frontend_plugin/qwenpaw-creator/files/ui/dist/app/index.html",
      );
      initialSrcRef.current = `${appUrl}?v=${encodeURIComponent(CREATOR_BUILD_ID)}#${creatorRouteFromHost()}`;
    }

    React.useEffect(() => {
      const receiveCreatorRoute = (event) => {
        if (
          event.source !== frameRef.current?.contentWindow ||
          event.data?.type !== NAVIGATION_MESSAGE
        ) {
          return;
        }
        const nextUrl = hostUrlForCreatorRoute(event.data.path);
        if (!nextUrl) return;
        const currentUrl = `${window.location.pathname}${window.location.search}${window.location.hash}`;
        if (nextUrl !== currentUrl) {
          window.history.replaceState(window.history.state, "", nextUrl);
        }
      };

      const restoreCreatorRoute = () => {
        frameRef.current?.contentWindow?.postMessage(
          {
            type: RESTORE_ROUTE_MESSAGE,
            path: creatorRouteFromHost(),
          },
          "*",
        );
      };

      window.addEventListener("message", receiveCreatorRoute);
      window.addEventListener("hashchange", restoreCreatorRoute);
      window.addEventListener("popstate", restoreCreatorRoute);
      return () => {
        window.removeEventListener("message", receiveCreatorRoute);
        window.removeEventListener("hashchange", restoreCreatorRoute);
        window.removeEventListener("popstate", restoreCreatorRoute);
      };
    }, []);

    return React.createElement(
      "div",
      {
        className: "qwenpaw-creator-slot-content",
        style: {
          position: "fixed",
          inset: 0,
          zIndex: 1000,
          width: "100vw",
          height: "100vh",
          overflow: "hidden",
          background: CREATOR_BG_COLOR,
        },
      },
      React.createElement("iframe", {
        ref: frameRef,
        title: "QwenPaw Creator",
        src: initialSrcRef.current,
        style: {
          width: "100%",
          height: "100%",
          border: 0,
          display: "block",
          background: CREATOR_BG_COLOR,
        },
        allow:
          "clipboard-read; clipboard-write; fullscreen; autoplay; picture-in-picture",
      }),
    );
  }

  slot.replace(pluginId, "creator.content", () => React.createElement(CreatorFrame), {
    id: "qwenpaw-creator.content",
  });
})();
