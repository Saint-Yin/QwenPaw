function Pt() {
  var tt, nt, rt, ot;
  const { React: e, antd: M, antdIcons: J, getApiUrl: q, getApiToken: U } = window.QwenPaw.host, {
    Card: F,
    Table: L,
    Tag: D,
    Typography: Te,
    Space: W,
    Button: b,
    Input: X,
    Radio: ke,
    Descriptions: de,
    Spin: he,
    message: Ue,
    theme: Ne
  } = M, { Text: ue } = Te, { TextArea: st } = X, { useState: T, useMemo: Ce, useCallback: _ } = e, { InfoCircleOutlined: Re, DownOutlined: Fe, RightOutlined: it } = J || {};
  function ct(t) {
    var s, i;
    const n = (i = (s = t == null ? void 0 : t.content) == null ? void 0 : s[0]) == null ? void 0 : i.data, r = n == null ? void 0 : n.arguments;
    if (typeof r == "string")
      try {
        return JSON.parse(r);
      } catch {
        return {};
      }
    return r ?? {};
  }
  function dt() {
    return window.currentSessionId ?? null;
  }
  function le(t) {
    return typeof t == "string" ? t : t && typeof t == "object" && "text" in t ? t.text : String(t ?? "");
  }
  function ut(t) {
    if (t == null) return !0;
    const n = le(t).trim();
    return !!(!n || /^[¥$]?0+(\.0+)?$/.test(n) || /^[-–—]+$/.test(n));
  }
  async function ft(t, n) {
    try {
      const r = U(), s = {
        "Content-Type": "application/json"
      };
      return r && (s.Authorization = `Bearer ${r}`), (await fetch(q("/interaction"), {
        method: "POST",
        headers: s,
        body: JSON.stringify({ session_id: t, result: n })
      })).ok;
    } catch {
      return !1;
    }
  }
  function mt(t) {
    if (!t) return null;
    if (typeof t == "string")
      try {
        const n = JSON.parse(t);
        if (Array.isArray(n)) {
          const r = n.find(
            (s) => (s == null ? void 0 : s.type) === "text" && (s == null ? void 0 : s.text)
          );
          return (r == null ? void 0 : r.text) ?? null;
        }
        if (typeof n == "string") return n;
      } catch {
        return t;
      }
    if (Array.isArray(t)) {
      const n = t.find((r) => (r == null ? void 0 : r.type) === "text" && (r == null ? void 0 : r.text));
      return (n == null ? void 0 : n.text) ?? null;
    }
    return null;
  }
  function pt(t) {
    var a, p;
    if (!t || t.length < 2) return null;
    const n = (p = (a = t[1]) == null ? void 0 : a.data) == null ? void 0 : p.output, r = mt(n);
    if (!r) return null;
    if (r.startsWith("Error:")) return r;
    const s = r.match(/^用户选择了「(.+?)」并确认部署$/);
    if (s) return `已确认部署「${s[1]}」`;
    const i = r.match(
      /^用户选择「(.+?)」并要求调整[：:](.+)$/
    );
    if (i)
      return `已选择「${i[1]}」并调整：${i[2]}`;
    if (r === "用户确认部署") return "已确认部署";
    const u = r.match(/^用户要求调整资源[：:](.+)$/);
    return u ? `已反馈调整意见：${u[1]}` : "已确认";
  }
  const Ke = [
    "资源类型",
    "资源用途",
    "规格",
    "地域",
    "数量",
    "计费方式",
    "时长",
    "原价",
    "优惠",
    "预估算费用"
  ], gt = new Set(
    Ke.map((t) => t.toLowerCase())
  );
  function Be(t) {
    if (!Array.isArray(t) || t.length !== 10) return !1;
    const n = le(t[0]).trim().toLowerCase();
    return gt.has(n);
  }
  function Ye(t) {
    if (!Array.isArray(t) || t.length !== 10) return !1;
    const n = le(t[0]).trim();
    return /^(合计|总计|total)/i.test(n);
  }
  function yt(t) {
    const n = [];
    let r = [];
    for (const s of t)
      r.push(s), Ye(s) && (n.push(r), r = []);
    return r.length > 0 && (n.length > 0 ? n[n.length - 1].push(...r) : n.push(r)), n.length > 0 ? n : [t];
  }
  function ht(t) {
    return typeof t == "string" ? t : t && typeof t == "object" && t.text ? t.url ? e.createElement(
      "a",
      {
        href: t.url,
        target: "_blank",
        rel: "noopener noreferrer"
      },
      t.text
    ) : t.text : String(t ?? "");
  }
  function Et({ data: t }) {
    var g, $, w;
    const { token: n } = Ne.useToken(), [r, s] = T("confirm"), [i, u] = T(""), [a, p] = T(!1), [l, R] = T(null), [A, N] = T(
      {}
    ), fe = e.useRef(!1), ee = e.useRef(null), [, te] = T(0), z = t == null ? void 0 : t.content, se = z && z.length >= 2 && (($ = (g = z[1]) == null ? void 0 : g.data) == null ? void 0 : $.output), ne = Ce(
      () => pt(z),
      [z]
    ), C = fe.current || se || ne !== null, x = Ce(() => {
      const d = ct(t), f = d == null ? void 0 : d.data;
      if (!f) return null;
      try {
        const h = typeof f == "string" ? JSON.parse(f) : f;
        let O;
        if (d.strategy_names)
          try {
            const v = typeof d.strategy_names == "string" ? JSON.parse(d.strategy_names) : d.strategy_names;
            O = Array.isArray(v) ? v : [];
          } catch {
            O = [];
          }
        else h != null && h.proposal_names ? O = h.proposal_names : O = [];
        const re = O.length >= 2 ? O.length : 0;
        let P;
        if (Array.isArray(h) && h.length > 0)
          if (Array.isArray(h[0]) && h[0].length === 10 && !Array.isArray(h[0][0])) {
            const B = h.filter(
              (oe) => !Be(oe)
            );
            if (B.filter(
              (oe) => Ye(oe)
            ).length >= 2)
              P = yt(B);
            else if (re >= 2 && B.length >= re * 2) {
              const oe = Math.ceil(B.length / re);
              P = [];
              for (let pe = 0; pe < B.length; pe += oe)
                P.push(B.slice(pe, pe + oe));
            } else
              P = [B];
          } else
            P = h.map(
              (B) => B.filter(
                (me) => Array.isArray(me) && me.length === 10 && !Be(me)
              )
            );
        else if (h != null && h.proposals)
          P = h.proposals.map(
            (v) => v.filter((B) => !Be(B))
          );
        else
          return null;
        if (P = P.filter((v) => v.length > 0), P.length === 0) return null;
        const Se = ["方案一", "方案二", "方案三", "方案四", "方案五"];
        if (O.length < P.length)
          for (let v = O.length; v < P.length; v++)
            O.push(Se[v] || `方案${v + 1}`);
        return { proposals: P, names: O };
      } catch {
        return null;
      }
    }, [t]), I = dt(), Y = (((w = x == null ? void 0 : x.proposals) == null ? void 0 : w.length) ?? 0) > 1, we = _(async () => {
      if (!I || C || !x) return;
      const d = Y ? l : 0, f = x.names[d ?? 0] || `方案${(d ?? 0) + 1}`;
      let h;
      r === "confirm" ? h = `用户选择了「${f}」并确认部署` : h = `用户选择「${f}」并要求调整：${i.trim() || "未填写具体要求"}`, p(!0);
      const O = await ft(I, h);
      p(!1), O ? (fe.current = !0, r === "confirm" ? ee.current = `已确认部署「${f}」` : ee.current = `已选择「${f}」并调整：${i.trim()}`, te((re) => re + 1), Ue.success(
        r === "confirm" ? "已确认部署方案" : "已提交调整意见"
      )) : Ue.error("操作失败，请重试");
    }, [
      I,
      C,
      x,
      r,
      i,
      l,
      Y
    ]), G = (t == null ? void 0 : t.status) === "in_progress" || (t == null ? void 0 : t.status) === "created";
    if (!x)
      return G ? e.createElement(
        "div",
        {
          style: {
            width: "100%",
            borderRadius: 10,
            border: `1px solid ${n.colorBorderSecondary}`,
            background: n.colorBgContainer,
            padding: "24px 16px",
            margin: "4px 0",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 12
          }
        },
        e.createElement(he, { size: "default" }),
        e.createElement(
          ue,
          { type: "secondary", style: { fontSize: 13 } },
          "正在生成资源方案..."
        )
      ) : e.createElement(
        F,
        { size: "small", style: { margin: "4px 0" } },
        e.createElement(ue, { type: "secondary" }, "无法解析方案数据")
      );
    const { proposals: ie, names: H } = x, ge = Ke.map((d, f) => ({
      title: d,
      dataIndex: `col_${f}`,
      key: `col_${f}`,
      render: (h) => ht(h),
      ellipsis: f < 3
    }));
    let Q = "待确认", V = "processing";
    C && (V = "success", Q = ee.current || ne || "已确认");
    const ye = e.createElement(
      D,
      {
        color: V,
        style: { marginLeft: 4 }
      },
      Q
    ), ce = e.createElement(
      W,
      { size: 8 },
      e.createElement("span", null, "☁️"),
      e.createElement(
        ue,
        { strong: !0, style: { fontSize: 14 } },
        C ? "资源配置方案" : "请确认您的资源配置方案"
      ),
      ye
    ), Z = ie.map((d, f) => {
      const h = Y ? l === f : !0, O = A[f] || !1, re = (k) => {
        const j = le(k[0] || "").trim();
        return /^合计|^总计|^total/i.test(j);
      }, P = d.find(re), Se = d.filter((k) => !re(k)), v = Se.map((k) => ({
        type: le(k[0] || ""),
        purpose: le(k[1] || ""),
        spec: le(k[2] || ""),
        cost: k[9] ?? null
      })), B = P ? le(P[9] ?? "") : "", me = d.map((k, j) => {
        const Pe = { key: j };
        return k.forEach((He, We) => {
          Pe[`col_${We}`] = He;
        }), Pe;
      }), oe = h ? `2px solid ${n.colorInfo}` : `1px solid ${n.colorBorderSecondary}`, pe = h ? `0 0 0 2px ${n.colorInfoBg}` : "none";
      return e.createElement(
        "div",
        {
          key: f,
          style: {
            flex: 1,
            minWidth: 240,
            border: oe,
            borderRadius: 8,
            cursor: Y ? "pointer" : "default",
            transition: "all 0.2s ease",
            boxShadow: pe,
            background: n.colorBgContainer
          },
          onClick: Y ? () => R(f) : void 0
        },
        e.createElement(
          "div",
          { style: { padding: "10px 12px" } },
          // Proposal name
          e.createElement(
            ue,
            {
              strong: !0,
              style: { fontSize: 14, display: "block", marginBottom: 8 }
            },
            H[f]
          ),
          ...v.map(
            (k, j) => e.createElement(
              "div",
              {
                key: j,
                style: {
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  padding: "4px 0",
                  borderBottom: j < v.length - 1 ? `1px solid ${n.colorSplit}` : "none"
                }
              },
              e.createElement(
                "div",
                { style: { flex: 1, minWidth: 0 } },
                e.createElement(
                  "span",
                  { style: { fontSize: 12, color: n.colorText } },
                  k.type
                ),
                k.spec && e.createElement(
                  "span",
                  {
                    style: {
                      fontSize: 11,
                      color: n.colorTextTertiary,
                      marginLeft: 6
                    }
                  },
                  k.spec
                )
              ),
              !ut(k.cost) && e.createElement(
                "span",
                {
                  style: {
                    fontSize: 12,
                    color: n.colorTextSecondary,
                    flexShrink: 0,
                    marginLeft: 8
                  }
                },
                le(k.cost)
              )
            )
          ),
          // Total cost
          B && e.createElement(
            "div",
            {
              style: {
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginTop: 6,
                paddingTop: 6,
                borderTop: `1px dashed ${n.colorBorder}`
              }
            },
            e.createElement(
              "span",
              { style: { fontSize: 12, fontWeight: 500 } },
              "合计"
            ),
            e.createElement(
              "span",
              {
                style: { fontSize: 14, fontWeight: 700, color: "#fa541c" }
              },
              B
            )
          ),
          // Details toggle
          e.createElement(
            "div",
            {
              style: {
                display: "flex",
                alignItems: "center",
                gap: 4,
                color: n.colorTextTertiary,
                fontSize: 12,
                cursor: "pointer",
                marginTop: 6
              },
              onClick: (k) => {
                k.stopPropagation(), N((j) => ({
                  ...j,
                  [f]: !j[f]
                }));
              }
            },
            e.createElement(
              O && Fe ? Fe : it || "span",
              {
                style: { fontSize: 10 }
              }
            ),
            e.createElement(
              "span",
              null,
              `明细 · ${Se.length} 项`
            )
          ),
          O && e.createElement(
            "div",
            {
              onClick: (k) => k.stopPropagation(),
              style: { marginTop: 4, maxHeight: 260, overflow: "auto" }
            },
            e.createElement(L, {
              columns: ge,
              dataSource: me,
              pagination: !1,
              size: "small",
              scroll: { x: "max-content" }
            })
          )
        )
      );
    }), c = e.createElement(
      "div",
      {
        style: {
          background: n.colorWarningBg,
          border: `1px solid ${n.colorWarningBorder}`,
          borderRadius: 6,
          padding: "8px 12px",
          marginBottom: 10,
          display: "flex",
          alignItems: "flex-start",
          gap: 8
        }
      },
      Re ? e.createElement(Re, {
        style: {
          color: n.colorWarning,
          fontSize: 14,
          flexShrink: 0,
          marginTop: 1
        }
      }) : e.createElement("span", null, "⚠️"),
      e.createElement(
        "span",
        {
          style: {
            fontSize: 12,
            color: n.colorWarningText,
            lineHeight: 1.5
          }
        },
        "在服务部署与配置过程中，可能因实际资源需求变化导致资源变配及费用调整，请及时关注实际资源使用情况与账单详情。"
      )
    ), S = !C && I && !(Y && l === null) && e.createElement(
      "div",
      null,
      e.createElement(
        "div",
        {
          style: {
            display: "flex",
            gap: 8,
            flexWrap: "wrap",
            marginBottom: 8
          }
        },
        // Confirm option
        e.createElement(
          "div",
          {
            style: {
              flex: 1,
              minWidth: 140,
              border: `1px solid ${r === "confirm" ? n.colorInfo : n.colorBorder}`,
              borderRadius: 6,
              padding: "8px 12px",
              cursor: "pointer",
              transition: "all 0.15s ease",
              display: "flex",
              alignItems: "center",
              gap: 8,
              background: r === "confirm" ? n.colorInfoBg : "transparent"
            },
            onClick: () => s("confirm")
          },
          e.createElement(ke, { checked: r === "confirm" }),
          e.createElement(
            "span",
            { style: { fontSize: 13 } },
            "确认部署"
          )
        ),
        // Adjust option
        e.createElement(
          "div",
          {
            style: {
              flex: 1,
              minWidth: 140,
              border: `1px solid ${r === "adjust" ? n.colorInfo : n.colorBorder}`,
              borderRadius: 6,
              padding: "8px 12px",
              transition: "all 0.15s ease",
              background: r === "adjust" ? n.colorInfoBg : "transparent"
            }
          },
          e.createElement(
            "div",
            {
              style: {
                display: "flex",
                alignItems: "center",
                gap: 8,
                cursor: "pointer"
              },
              onClick: () => s("adjust")
            },
            e.createElement(ke, { checked: r === "adjust" }),
            e.createElement(
              "span",
              { style: { fontSize: 13 } },
              "调整资源"
            )
          ),
          r === "adjust" && e.createElement(st, {
            value: i,
            onChange: (d) => u(d.target.value),
            placeholder: "请输入调整要求",
            autoSize: { minRows: 1, maxRows: 3 },
            style: { fontSize: 12, marginTop: 6 }
          })
        )
      ),
      // Footer
      e.createElement(
        "div",
        {
          style: {
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            paddingTop: 8
          }
        },
        e.createElement(
          ue,
          { type: "secondary", style: { fontSize: 11 } },
          Y ? "一小时后未操作将自动选择第一个方案" : "一小时后未操作将自动确认部署"
        ),
        e.createElement(
          b,
          {
            type: "primary",
            size: "small",
            loading: a,
            onClick: we,
            disabled: r === "adjust" && !i.trim()
          },
          r === "confirm" ? "确认部署" : "提交调整"
        )
      )
    ), y = Y && l === null && !C && e.createElement(
      "div",
      {
        style: {
          textAlign: "center",
          padding: "8px 0 4px",
          color: n.colorTextQuaternary,
          fontSize: 12
        }
      },
      "请点击选择一个方案后继续操作"
    );
    return e.createElement(
      "div",
      {
        style: {
          width: "100%",
          borderRadius: 10,
          border: `1px solid ${n.colorBorder}`,
          overflow: "hidden",
          background: n.colorBgContainer,
          padding: "12px 16px",
          margin: "4px 0"
        }
      },
      // Header
      e.createElement("div", { style: { marginBottom: 10 } }, ce),
      // Proposals grid
      e.createElement(
        "div",
        {
          style: {
            display: "flex",
            gap: 10,
            marginBottom: 12,
            flexWrap: "wrap"
          }
        },
        ...Z
      ),
      y,
      c,
      !C && S
    );
  }
  const {
    Form: ae,
    Select: ze,
    Drawer: xt,
    Modal: qe,
    Empty: wt,
    Badge: Xe,
    Divider: St,
    message: K
  } = M, {
    ApiOutlined: Ge,
    PlusOutlined: Qe,
    ReloadOutlined: $e,
    DeleteOutlined: Ve,
    LinkOutlined: Ze
  } = J || {}, { useEffect: et } = e, Ee = "/a2a/agents";
  function Oe() {
    var t;
    try {
      const n = sessionStorage.getItem("qwenpaw-agent-storage") || localStorage.getItem("qwenpaw-agent-storage");
      if (n) {
        const r = JSON.parse(n);
        return ((t = r == null ? void 0 : r.state) == null ? void 0 : t.selectedAgent) || null;
      }
    } catch {
    }
    return null;
  }
  async function xe(t, n) {
    const r = q(t), s = U == null ? void 0 : U(), i = Oe(), u = {
      "Content-Type": "application/json",
      ...s ? { Authorization: `Bearer ${s}` } : {},
      ...i ? { "X-Agent-Id": i } : {}
    }, a = await fetch(r, {
      ...n,
      headers: { ...u, ...(n == null ? void 0 : n.headers) || {} }
    });
    if (!a.ok) {
      const p = await a.text().catch(() => "");
      throw new Error(p || `HTTP ${a.status}`);
    }
    return a.status === 204 || a.headers.get("content-length") === "0" ? null : a.json();
  }
  function At(t) {
    var p;
    const { agent: n, onClick: r } = t, s = n.status === "connected", i = s ? "#52c41a" : n.status === "error" ? "#ff4d4f" : "#d9d9d9", u = s ? "已连接" : n.status === "error" ? "错误" : "未连接", a = {
      gateway: "阿里云Agent Hub",
      bearer: "Bearer Token",
      api_key: "API Key"
    };
    return e.createElement(
      F,
      {
        hoverable: !0,
        onClick: r,
        size: "small",
        style: { cursor: "pointer" },
        title: e.createElement(
          W,
          null,
          e.createElement(Xe, { color: i }),
          e.createElement(
            "span",
            null,
            n.name || n.alias || n.url
          )
        ),
        extra: n.auth_type ? e.createElement(
          D,
          { color: "blue" },
          a[n.auth_type] || n.auth_type
        ) : null
      },
      e.createElement(
        "div",
        { style: { fontSize: 12, color: "#666" } },
        e.createElement(
          "div",
          { style: { marginBottom: 4 } },
          Ze ? e.createElement(Ze, { style: { marginRight: 4 } }) : null,
          n.url
        ),
        n.description ? e.createElement(
          "div",
          { style: { marginBottom: 4, color: "#999" } },
          n.description
        ) : null,
        ((p = n.skills) == null ? void 0 : p.length) > 0 ? e.createElement(
          "div",
          null,
          n.skills.slice(0, 3).map(
            (l, R) => e.createElement(
              D,
              { key: R, style: { fontSize: 11 } },
              l.name
            )
          ),
          n.skills.length > 3 ? e.createElement(
            D,
            { style: { fontSize: 11 } },
            `+${n.skills.length - 3}`
          ) : null
        ) : null,
        e.createElement(
          "div",
          { style: { marginTop: 4, color: i, fontSize: 11 } },
          u,
          n.error ? ` - ${n.error}` : ""
        )
      )
    );
  }
  function bt() {
    const t = e.useRef(Oe()), [n, r] = T(t.current);
    return et(() => {
      const s = () => {
        const u = Oe();
        u !== t.current && (t.current = u, r(u));
      }, i = setInterval(s, 200);
      return window.addEventListener("storage", s), () => {
        clearInterval(i), window.removeEventListener("storage", s);
      };
    }, []), n;
  }
  function Tt() {
    var lt, at;
    const { token: t } = Ne.useToken(), n = bt(), [r, s] = T([]), [i, u] = T(!0), [a, p] = T(!1), [l, R] = T(null), [A, N] = T(!1), [fe, ee] = T(!1), [te, z] = T(!1), [se, ne] = T(!1), [C, x] = T(""), [I] = ae.useForm(), [Y, we] = T(!1), [G, ie] = T(!1), [H, ge] = T([]), [Q, V] = T(
      /* @__PURE__ */ new Set()
    ), [ye, ce] = T(
      []
    ), Z = e.useRef(null), c = Ce(
      () => new Set(r.map((o) => o.url)),
      [r]
    ), S = e.useRef(c);
    S.current = c;
    const y = _(async () => {
      u(!0);
      try {
        const o = await xe(Ee);
        s((o == null ? void 0 : o.agents) || []);
      } catch {
        s([]);
      } finally {
        u(!1);
      }
    }, []);
    et(() => {
      y();
    }, [n]);
    const g = _(() => {
      N(!0), R(null), p(!0), I.resetFields(), I.setFieldsValue({
        url: "",
        alias: "",
        auth_type: "",
        auth_token: ""
      });
    }, [I]), $ = _((o) => {
      N(!1), R(o), p(!0);
    }, []), w = _(() => {
      ne(!1), x("");
    }, []), d = _(async () => {
      if (!l || !C.trim()) return;
      const o = l.alias || l.url;
      if (C.trim() === o) {
        w();
        return;
      }
      try {
        const m = await xe(
          `${Ee}?alias=${encodeURIComponent(o)}`,
          {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ new_alias: C.trim() })
          }
        );
        K.success("别名已修改"), ne(!1), R(m), await y();
      } catch (m) {
        K.error(m.message || "修改失败");
      }
    }, [l, C, y, w]), f = _(() => {
      w(), p(!1), R(null), N(!1), I.resetFields();
    }, [w, I]), h = _(async () => {
      let o;
      try {
        o = await I.validateFields();
      } catch {
        return;
      }
      const m = {
        url: String(o.url || "").trim(),
        alias: String(o.alias || "").trim() || void 0,
        auth_type: String(o.auth_type || ""),
        auth_token: String(o.auth_token || "")
      };
      if (m.url) {
        ee(!0);
        try {
          await xe(Ee, {
            method: "POST",
            body: JSON.stringify(m)
          }), K.success("A2A Agent 注册成功"), await y(), f();
        } catch (E) {
          K.error(E.message || "注册失败");
        } finally {
          ee(!1);
        }
      }
    }, [I, y, f]), O = _(async () => {
      if (!l) return;
      const o = l.alias || l.url, m = l.name || o;
      qe.confirm({
        title: "确认删除",
        content: `确定删除 A2A Agent「${m}」吗？此操作不可撤销。`,
        okText: "删除",
        cancelText: "取消",
        okButtonProps: { danger: !0 },
        async onOk() {
          try {
            await xe(`${Ee}?alias=${encodeURIComponent(o)}`, {
              method: "DELETE"
            }), K.success(`已删除 A2A Agent「${m}」`), await y(), f();
          } catch (E) {
            K.error(E.message || "删除失败");
          }
        }
      });
    }, [l, y, f]), re = _(async () => {
      if (!l) return;
      const o = l.alias || l.url;
      z(!0);
      try {
        const m = await xe(
          `${Ee}/refresh?alias=${encodeURIComponent(o)}`,
          {
            method: "POST"
          }
        );
        K.success("Agent Card 已刷新"), await y(), m && R(m);
      } catch (m) {
        K.error(m.message || "刷新失败");
      } finally {
        z(!1);
      }
    }, [l, y]), P = _(() => {
      l && (x(l.alias || ""), ne(!0));
    }, [l]), Se = _(() => {
      we(!0), ge([]), V(/* @__PURE__ */ new Set()), ce([]), Z.current = null, B();
    }, []), v = _(() => {
      G && Z.current && Z.current.abort(), we(!1), ge([]), V(/* @__PURE__ */ new Set()), ce([]), Z.current = null;
    }, [G]), B = _(async () => {
      ie(!0);
      const o = new AbortController();
      Z.current = o;
      try {
        const m = U == null ? void 0 : U(), E = Oe(), Ie = {
          ...m ? { Authorization: `Bearer ${m}` } : {},
          ...E ? { "X-Agent-Id": E } : {}
        }, be = await fetch(q("/a2a/import"), {
          method: "GET",
          headers: Ie,
          signal: o.signal
        });
        if (!be.ok) {
          const _e = await be.text().catch(() => "");
          throw new Error(_e || `HTTP ${be.status}`);
        }
        const je = await be.json(), Je = (je == null ? void 0 : je.agents) || [];
        if (Je.length === 0) {
          K.warning("未找到可用的 Agent");
          return;
        }
        ge(Je);
        const Ot = S.current;
        V(
          new Set(
            Je.filter((_e) => !Ot.has(_e.url)).map((_e) => _e.url)
          )
        );
      } catch (m) {
        if ((m == null ? void 0 : m.name) === "AbortError") return;
        K.error(m.message || "获取 Agent 列表失败");
      } finally {
        ie(!1), Z.current = null;
      }
    }, []), me = _((o) => {
      V((m) => {
        const E = new Set(m);
        return E.has(o) ? E.delete(o) : E.add(o), E;
      });
    }, []), oe = _(() => {
      V(
        new Set(
          H.filter((o) => !c.has(o.url)).map((o) => o.url)
        )
      );
    }, [H, c]), pe = _(() => {
      V(/* @__PURE__ */ new Set());
    }, []), k = _(async () => {
      const o = H.filter(
        (E) => Q.has(E.url) && !c.has(E.url)
      );
      if (o.length === 0) {
        K.warning("请至少选择一个 Agent");
        return;
      }
      ie(!0), ce([]);
      const m = [];
      for (const E of o) {
        try {
          await xe(Ee, {
            method: "POST",
            body: JSON.stringify({
              url: E.url,
              alias: E.name || void 0,
              auth_type: E.auth_type || "gateway",
              auth_token: ""
            })
          }), m.push({ name: E.name || E.url, success: !0 });
        } catch (Ie) {
          m.push({
            name: E.name || E.url,
            success: !1,
            error: Ie.message || "注册失败"
          });
        }
        ce([...m]);
      }
      await y(), K.success(
        `导入完成：成功 ${m.filter((E) => E.success).length} 个，失败 ${m.filter((E) => !E.success).length} 个`
      ), ie(!1), setTimeout(() => v(), 800);
    }, [H, Q, y, c]), j = ((lt = ae.useWatch) == null ? void 0 : lt.call(ae, "auth_type", I)) ?? "", Pe = e.createElement(
      ae,
      { form: I, layout: "vertical" },
      e.createElement(
        ae.Item,
        {
          name: "url",
          label: "Agent URL",
          rules: [{ required: !0, message: "请输入 Agent URL" }]
        },
        e.createElement(X, {
          placeholder: "https://agent.example.com"
        })
      ),
      e.createElement(
        ae.Item,
        { name: "alias", label: "别名" },
        e.createElement(X, { placeholder: "输入别名（可选）" })
      ),
      e.createElement(
        ae.Item,
        { name: "auth_type", label: "认证类型" },
        e.createElement(
          ze,
          { allowClear: !0, placeholder: "无认证" },
          e.createElement(
            ze.Option,
            { value: "bearer" },
            "Bearer Token"
          ),
          e.createElement(ze.Option, { value: "api_key" }, "API Key"),
          e.createElement(
            ze.Option,
            { value: "gateway" },
            "阿里云Agent Hub"
          )
        )
      ),
      j === "gateway" ? e.createElement(
        "div",
        {
          style: {
            marginBottom: 16,
            padding: "8px 12px",
            background: "#f6ffed",
            border: "1px solid #b7eb8f",
            borderRadius: 6,
            fontSize: 12,
            color: "#52c41a"
          }
        },
        "阿里云Agent Hub 模式将自动使用环境变量中的 AK-SK 换取 Bearer Token"
      ) : null,
      j && j !== "gateway" ? e.createElement(
        ae.Item,
        { name: "auth_token", label: "认证凭证" },
        e.createElement(X.Password, {
          placeholder: "Bearer Token 或 API Key"
        })
      ) : null
    ), He = l ? e.createElement(
      "div",
      null,
      e.createElement(
        de,
        { column: 1, bordered: !0, size: "small" },
        e.createElement(
          de.Item,
          { label: "URL" },
          l.url
        ),
        e.createElement(
          de.Item,
          { label: "别名" },
          se ? e.createElement(
            "div",
            {
              style: { display: "flex", alignItems: "center", gap: 6 }
            },
            e.createElement(X, {
              value: C,
              onChange: (o) => x(o.target.value),
              onPressEnter: d,
              autoFocus: !0,
              placeholder: "输入新别名",
              size: "small",
              style: { flex: 1 }
            }),
            e.createElement(
              b,
              {
                type: "link",
                size: "small",
                onClick: d,
                disabled: !C.trim(),
                style: { padding: 0 }
              },
              "保存"
            )
          ) : e.createElement(
            "div",
            {
              style: { display: "flex", alignItems: "center", gap: 8 }
            },
            e.createElement("span", null, l.alias || "-"),
            e.createElement(
              "a",
              {
                style: { fontSize: 12 },
                onClick: P
              },
              "修改"
            )
          )
        ),
        e.createElement(
          de.Item,
          { label: "Agent 名称" },
          l.name || "-"
        ),
        e.createElement(
          de.Item,
          { label: "状态" },
          e.createElement(Xe, {
            color: l.status === "connected" ? "#52c41a" : l.status === "error" ? "#ff4d4f" : "#d9d9d9",
            text: l.status === "connected" ? "已连接" : l.status === "error" ? "错误" : "未连接"
          })
        ),
        e.createElement(
          de.Item,
          { label: "认证类型" },
          l.auth_type ? e.createElement(
            D,
            { color: "blue" },
            {
              gateway: "阿里云Agent Hub",
              bearer: "Bearer Token",
              api_key: "API Key"
            }[l.auth_type] || l.auth_type
          ) : "无认证"
        ),
        e.createElement(
          de.Item,
          { label: "描述" },
          l.description || "-"
        ),
        e.createElement(
          de.Item,
          { label: "版本" },
          l.version || "-"
        )
      ),
      ((at = l.skills) == null ? void 0 : at.length) > 0 ? e.createElement(
        "div",
        { style: { marginTop: 16 } },
        e.createElement("h4", null, "技能"),
        ...l.skills.map(
          (o, m) => e.createElement(
            F,
            { key: m, size: "small", style: { marginBottom: 8 } },
            e.createElement("strong", null, o.name),
            o.description ? e.createElement(
              "div",
              { style: { color: "#666", fontSize: 12 } },
              o.description
            ) : null
          )
        )
      ) : null,
      l.capabilities ? e.createElement(
        "div",
        { style: { marginTop: 16 } },
        e.createElement("h4", null, "能力"),
        e.createElement(
          W,
          null,
          e.createElement(
            D,
            {
              color: l.capabilities.streaming ? "green" : "default"
            },
            "Streaming"
          ),
          e.createElement(
            D,
            {
              color: l.capabilities.push_notifications ? "green" : "default"
            },
            "Push Notifications"
          )
        )
      ) : null,
      l.error ? e.createElement(
        "div",
        {
          style: {
            marginTop: 16,
            padding: "8px 12px",
            background: "#fff2f0",
            border: "1px solid #ffccc7",
            borderRadius: 6,
            fontSize: 12,
            color: "#ff4d4f"
          }
        },
        l.error
      ) : null,
      e.createElement(St, null),
      e.createElement(
        W,
        null,
        e.createElement(
          b,
          {
            type: "primary",
            icon: $e ? e.createElement($e) : null,
            loading: te,
            onClick: re
          },
          "刷新 Agent Card"
        ),
        e.createElement(
          b,
          {
            danger: !0,
            icon: Ve ? e.createElement(Ve) : null,
            onClick: O
          },
          "删除"
        )
      )
    ) : null, We = e.createElement(
      xt,
      {
        title: A ? "注册远程 A2A Agent" : (l == null ? void 0 : l.name) || (l == null ? void 0 : l.alias) || "Agent 详情",
        open: a,
        onClose: f,
        width: 480,
        footer: A ? e.createElement(
          W,
          { style: { display: "flex", justifyContent: "flex-end" } },
          e.createElement(b, { onClick: f }, "取消"),
          e.createElement(
            b,
            { type: "primary", loading: fe, onClick: h },
            "注册"
          )
        ) : null
      },
      A ? Pe : He
    ), Rt = e.createElement(
      "div",
      { style: { marginBottom: 16 } },
      e.createElement(
        "div",
        {
          style: {
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center"
          }
        },
        e.createElement("h2", { style: { margin: 0 } }, "A2A 远程 Agent"),
        e.createElement(
          W,
          null,
          e.createElement(
            b,
            {
              icon: $e ? e.createElement($e) : null,
              onClick: y,
              loading: i
            },
            "刷新列表"
          ),
          e.createElement(
            b,
            {
              icon: Ge ? e.createElement(Ge) : null,
              onClick: Se
            },
            "从阿里云AgentHub导入"
          ),
          e.createElement(
            b,
            {
              type: "primary",
              icon: Qe ? e.createElement(Qe) : null,
              onClick: g
            },
            "注册 Agent"
          )
        )
      ),
      e.createElement(
        "div",
        {
          style: {
            marginTop: 8,
            fontSize: 12,
            color: "#8c8c8c",
            lineHeight: 1.6
          }
        },
        Re ? e.createElement(Re, {
          style: { marginRight: 4, color: "#faad14" }
        }) : null,
        "当前 A2A 功能仅支持 CloudPaw 插件连接阿里云 Skills 门户 Agent，连接其他 Agent 可能存在不兼容问题。"
      )
    ), zt = i ? e.createElement(
      "div",
      { style: { textAlign: "center", padding: 60 } },
      e.createElement(he, { size: "large" })
    ) : r.length === 0 ? e.createElement(wt, {
      description: "暂无注册的远程 A2A Agent"
    }) : e.createElement(
      "div",
      {
        style: {
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))",
          gap: 12
        }
      },
      ...r.map(
        (o) => e.createElement(At, {
          key: o.alias || o.url,
          agent: o,
          onClick: () => $(o)
        })
      )
    ), Ae = ye.length > 0, $t = e.createElement(
      qe,
      {
        title: Ae ? "导入结果" : "从阿里云AgentHub导入 Agent",
        open: Y,
        onCancel: v,
        closable: !G || Ae,
        maskClosable: !G || Ae,
        width: 800,
        footer: Ae ? e.createElement(
          W,
          { style: { display: "flex", justifyContent: "flex-end" } },
          e.createElement(
            b,
            { type: "primary", onClick: v },
            "关闭"
          )
        ) : H.length > 0 ? e.createElement(
          W,
          { style: { display: "flex", justifyContent: "flex-end" } },
          e.createElement(
            b,
            { onClick: v },
            "取消"
          ),
          e.createElement(
            b,
            {
              type: "primary",
              loading: G,
              disabled: Q.size === 0,
              onClick: k
            },
            `确认导入 (${Q.size}/${H.length})`
          )
        ) : null
      },
      // Loading state
      G && H.length === 0 && e.createElement(
        "div",
        {
          style: {
            textAlign: "center",
            padding: 40,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 12
          }
        },
        e.createElement(he, { size: "large" }),
        e.createElement(
          "span",
          { style: { fontSize: 13, color: t.colorTextTertiary } },
          "正在从 AgentHub 获取 Agent 列表..."
        )
      ),
      // Agent selection list (hide after import completed)
      !G && !Ae && H.length > 0 && e.createElement(
        "div",
        null,
        // Header bar
        e.createElement(
          "div",
          {
            style: {
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: 8,
              fontSize: 12,
              color: t.colorTextTertiary
            }
          },
          e.createElement(
            "span",
            null,
            `共 ${H.length} 个 Agent，已选 ${Q.size} 个`
          ),
          e.createElement(
            W,
            { size: 4 },
            e.createElement(
              b,
              {
                size: "small",
                type: "link",
                style: { padding: 0, height: "auto" },
                onClick: oe
              },
              "全选"
            ),
            e.createElement(
              b,
              {
                size: "small",
                type: "link",
                style: { padding: 0, height: "auto" },
                onClick: pe
              },
              "取消全选"
            )
          )
        ),
        // Agent list
        e.createElement(
          "div",
          {
            style: {
              display: "flex",
              flexDirection: "column",
              gap: 8,
              maxHeight: 420,
              overflowY: "auto"
            }
          },
          ...H.map((o) => {
            var E;
            const m = Q.has(o.url);
            return e.createElement(
              "div",
              {
                key: o.url,
                style: {
                  display: "flex",
                  gap: 8,
                  padding: 10,
                  border: m ? `1px solid ${t.colorInfo}` : `1px solid ${t.colorBorderSecondary}`,
                  borderRadius: 6,
                  cursor: c.has(o.url) ? "default" : "pointer",
                  background: c.has(o.url) ? t.colorBgLayout : m ? t.colorInfoBg : t.colorBgContainer,
                  transition: "all 0.15s ease",
                  opacity: c.has(o.url) ? 0.7 : 1
                },
                onClick: () => {
                  c.has(o.url) || me(o.url);
                }
              },
              e.createElement(
                "div",
                { style: { flex: 1, minWidth: 0 } },
                e.createElement(
                  "div",
                  {
                    style: {
                      fontWeight: 500,
                      fontSize: 13,
                      marginBottom: 2
                    }
                  },
                  o.name || o.url
                ),
                o.description ? e.createElement(
                  "div",
                  {
                    style: {
                      fontSize: 11,
                      color: t.colorTextTertiary,
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap"
                    }
                  },
                  o.description
                ) : null,
                ((E = o.skills) == null ? void 0 : E.length) > 0 ? e.createElement(
                  "div",
                  { style: { marginTop: 4 } },
                  ...o.skills.slice(0, 3).map(
                    (Ie, be) => e.createElement(
                      D,
                      {
                        key: be,
                        color: t.colorInfoHover,
                        style: {
                          fontSize: 10,
                          marginRight: 4,
                          fontWeight: 500
                        }
                      },
                      Ie.name
                    )
                  ),
                  o.skills.length > 3 ? e.createElement(
                    D,
                    { style: { fontSize: 10 } },
                    `+${o.skills.length - 3}`
                  ) : null
                ) : null
              ),
              c.has(o.url) ? e.createElement(
                D,
                {
                  color: t.colorSuccess,
                  style: {
                    fontWeight: 600,
                    fontSize: 11,
                    flexShrink: 0,
                    padding: "2px 8px",
                    lineHeight: "18px",
                    height: 22,
                    borderRadius: 4
                  }
                },
                "✓ 已导入"
              ) : null
            );
          })
        )
      ),
      // Import results
      Ae && e.createElement(
        "div",
        {
          style: {
            maxHeight: 350,
            overflowY: "auto",
            display: "flex",
            flexDirection: "column",
            gap: 6
          }
        },
        ...ye.map(
          (o, m) => e.createElement(
            "div",
            {
              key: m,
              style: {
                display: "flex",
                alignItems: "center",
                gap: 8,
                padding: "6px 10px",
                borderRadius: 4,
                background: o.success ? t.colorInfoBg : t.colorErrorBg,
                border: o.success ? `1px solid ${t.colorInfo}` : `1px solid ${t.colorErrorBorder}`,
                fontSize: 12
              }
            },
            e.createElement(
              "span",
              {
                style: {
                  color: o.success ? t.colorSuccess : t.colorError,
                  fontSize: 14
                }
              },
              o.success ? "✓" : "✗"
            ),
            e.createElement(
              "span",
              {
                style: {
                  flex: 1,
                  color: o.success ? t.colorText : t.colorError
                }
              },
              o.name,
              o.error ? ` - ${o.error}` : ""
            )
          )
        )
      )
    );
    return e.createElement(
      "div",
      { style: { padding: 24 } },
      Rt,
      zt,
      We,
      $t
    );
  }
  function kt({ data: t }) {
    var ye, ce, Z;
    const { token: n } = Ne.useToken(), r = e.useRef(null), [s, i] = T({}), u = Ce(() => {
      var S, y, g;
      const c = (g = (y = (S = t == null ? void 0 : t.content) == null ? void 0 : S[0]) == null ? void 0 : y.data) == null ? void 0 : g.arguments;
      if (!c) return null;
      try {
        return JSON.parse(c);
      } catch {
        return null;
      }
    }, [(Z = (ce = (ye = t == null ? void 0 : t.content) == null ? void 0 : ye[0]) == null ? void 0 : ce.data) == null ? void 0 : Z.arguments]), { toolResult: a, rawErrorText: p } = Ce(() => {
      var S;
      const c = t == null ? void 0 : t.content;
      if (!Array.isArray(c))
        return { toolResult: null, rawErrorText: "" };
      for (const y of c) {
        const g = (S = y == null ? void 0 : y.data) == null ? void 0 : S.output;
        if (!g) continue;
        let $ = "";
        if (Array.isArray(g)) {
          const w = g.find(
            (d) => (d == null ? void 0 : d.type) === "text" && (d == null ? void 0 : d.text)
          );
          $ = (w == null ? void 0 : w.text) || "";
        } else if (typeof g == "string")
          try {
            const w = JSON.parse(g);
            if (typeof w == "object" && (w != null && w.steps || w != null && w.response_text))
              return { toolResult: w, rawErrorText: "" };
            if (Array.isArray(w)) {
              const d = w.find((f) => (f == null ? void 0 : f.type) === "text" && (f == null ? void 0 : f.text));
              d != null && d.text && ($ = d.text);
            }
          } catch {
            $ = g;
          }
        if ($)
          try {
            return { toolResult: JSON.parse($), rawErrorText: "" };
          } catch {
            return { toolResult: null, rawErrorText: $ };
          }
      }
      return { toolResult: null, rawErrorText: "" };
    }, [t == null ? void 0 : t.content]), l = (a == null ? void 0 : a.steps) || [], R = (a == null ? void 0 : a.task_state) || "", A = (a == null ? void 0 : a.error) || "", N = (a == null ? void 0 : a.response_text) || "";
    e.useEffect(() => {
      r.current && (r.current.scrollTop = r.current.scrollHeight);
    }, [l.length, N, p]), e.useEffect(() => {
      const c = { ...s };
      let S = !1;
      l.forEach((y, g) => {
        s[g] === void 0 && (y.type === "thinking" && y.done || y.type === "tool_call" && y.status !== "running") && (c[g] = !0, S = !0);
      }), S && i(c);
    }, [l]);
    const fe = (u == null ? void 0 : u.agent_alias) || "", ee = (u == null ? void 0 : u.agent_url) || "", te = fe || ee || "远程 Agent", z = {
      completed: { color: "#52c41a", text: "已完成" },
      TASK_STATE_COMPLETED: { color: "#52c41a", text: "已完成" },
      failed: { color: "#ff4d4f", text: "失败" },
      TASK_STATE_FAILED: { color: "#ff4d4f", text: "失败" },
      error: { color: "#ff4d4f", text: "出错" },
      canceled: { color: "#faad14", text: "已取消" },
      TASK_STATE_CANCELED: { color: "#faad14", text: "已取消" },
      AWAITING_USER_INPUT: { color: "#1677ff", text: "等待输入" },
      input_required: { color: "#1677ff", text: "等待输入" }
    }, C = (a !== null || !!p) && !(R === "working" || R === "TASK_STATE_WORKING");
    let x = "#1677ff", I = "执行中...";
    C && (z[R] ? (x = z[R].color, I = z[R].text) : p ? (x = "#ff4d4f", I = "出错") : (x = "#52c41a", I = "已完成"));
    const Y = e.createElement(
      W,
      { size: 6 },
      e.createElement("span", { style: { fontSize: 13 } }, "🔗"),
      e.createElement(
        ue,
        { style: { fontSize: 12, color: "#595959" } },
        `A2A: ${te}`
      ),
      e.createElement(
        D,
        { color: x, style: { fontSize: 11, lineHeight: "18px" } },
        I
      )
    ), we = l.length === 0 && !p && !A, G = !C && we ? e.createElement(
      "div",
      {
        style: {
          display: "flex",
          alignItems: "center",
          gap: 8,
          padding: "6px 10px",
          marginBottom: 8,
          background: "#f6ffed",
          border: "1px solid #b7eb8f",
          borderRadius: 6
        }
      },
      e.createElement(he, { size: "small" }),
      e.createElement(
        ue,
        { style: { fontSize: 12, color: "#52c41a" } },
        `正在连接 ${te}...`
      )
    ) : null;
    function ie(c) {
      i((S) => ({
        ...S,
        [c]: !S[c]
      }));
    }
    function H(c, S) {
      const y = !!s[S];
      if (c.type === "thinking") {
        const g = !!c.done, $ = g ? "💭" : "🧠", w = g ? "思考完成" : "思考中...", d = e.createElement(
          "div",
          {
            key: `step-${S}`,
            style: {
              display: "flex",
              alignItems: "center",
              gap: 6,
              padding: "3px 0",
              cursor: g ? "pointer" : "default",
              fontSize: 12,
              color: "#8c8c8c"
            },
            onClick: g ? () => ie(S) : void 0
          },
          g && e.createElement(
            "span",
            { style: { fontSize: 10, color: "#bfbfbf" } },
            y ? "▶" : "▼"
          ),
          e.createElement("span", null, $),
          e.createElement("span", null, w),
          !g && e.createElement(he, {
            size: "small",
            style: { marginLeft: 4 }
          })
        );
        return y ? d : e.createElement(
          "div",
          { key: `step-${S}` },
          d,
          e.createElement(
            "div",
            {
              style: {
                marginLeft: 20,
                padding: "4px 8px",
                background: "#fafafa",
                borderRadius: 4,
                fontSize: 12,
                color: "#595959",
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
                maxHeight: 120,
                overflowY: "auto",
                lineHeight: "1.5"
              }
            },
            c.text || ""
          )
        );
      }
      if (c.type === "tool_call") {
        const g = c.status === "running", $ = c.status === "error", w = g ? "⚙️" : $ ? "❌" : "✅", d = g ? `正在执行: ${c.name}` : $ ? `执行失败: ${c.name}` : `执行完成: ${c.name}`, f = g ? "#1677ff" : $ ? "#ff4d4f" : "#52c41a", h = e.createElement(
          "div",
          {
            key: `step-${S}`,
            style: {
              display: "flex",
              alignItems: "center",
              gap: 6,
              padding: "3px 0",
              cursor: g ? "default" : "pointer",
              fontSize: 12,
              color: f
            },
            onClick: g ? void 0 : () => ie(S)
          },
          !g && e.createElement(
            "span",
            { style: { fontSize: 10, color: "#bfbfbf" } },
            y ? "▶" : "▼"
          ),
          e.createElement("span", null, w),
          e.createElement("span", null, d),
          g && e.createElement(he, {
            size: "small",
            style: { marginLeft: 4 }
          })
        );
        return y || !c.desc && !g ? h : e.createElement(
          "div",
          { key: `step-${S}` },
          h,
          c.desc && e.createElement(
            "div",
            {
              style: {
                marginLeft: 20,
                padding: "2px 8px",
                fontSize: 11,
                color: n.colorTextTertiary
              }
            },
            c.desc
          )
        );
      }
      return c.type === "text" ? e.createElement(
        "div",
        {
          key: `step-${S}`,
          style: {
            padding: "4px 0",
            fontSize: 12,
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            lineHeight: "1.6",
            color: "#262626"
          }
        },
        c.text || ""
      ) : null;
    }
    const ge = l.length > 0 ? e.createElement(
      "div",
      {
        ref: r,
        style: {
          background: "#fafafa",
          border: "1px solid #e8e8e8",
          borderRadius: 6,
          padding: "6px 10px",
          maxHeight: 200,
          overflowY: "auto"
        }
      },
      ...l.map(H)
    ) : null, Q = p || A ? e.createElement(
      "div",
      {
        style: {
          background: "#fff2f0",
          border: "1px solid #ffccc7",
          borderRadius: 6,
          padding: "8px 12px",
          fontSize: 12,
          color: "#ff4d4f",
          whiteSpace: "pre-wrap",
          wordBreak: "break-word"
        }
      },
      A ? `错误: ${A}` : p
    ) : null, V = !l.length && N && !p ? e.createElement(
      "div",
      {
        ref: r,
        style: {
          background: "#fafafa",
          border: "1px solid #e8e8e8",
          borderRadius: 6,
          padding: "10px 12px",
          maxHeight: 200,
          overflowY: "auto"
        }
      },
      e.createElement(
        ue,
        {
          style: {
            fontSize: 12,
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            lineHeight: "1.6"
          }
        },
        N
      )
    ) : null;
    return e.createElement(
      "div",
      {
        style: {
          width: "100%",
          borderRadius: 8,
          border: "1px solid #f0f0f0",
          overflow: "hidden",
          background: "#fff",
          padding: "8px 12px",
          margin: "4px 0"
        }
      },
      e.createElement("div", { style: { marginBottom: 6 } }, Y),
      G,
      ge,
      V,
      Q
    );
  }
  const Ct = "__A2A_STREAM_START__", vt = "A2A_STREAM_START", ve = /* @__PURE__ */ new Set();
  function Me(t) {
    return t ? t.includes(Ct) || t.includes(vt) : !1;
  }
  function Le(t) {
    var n, r;
    return t.getAttribute("data-msg-id") || t.getAttribute("data-message-id") || ((n = t.closest("[data-msg-id]")) == null ? void 0 : n.getAttribute("data-msg-id")) || ((r = t.closest("[data-message-id]")) == null ? void 0 : r.getAttribute("data-message-id")) || null;
  }
  function It(t) {
    if (Me(t.innerHTML) || Me(t.textContent))
      return t;
    const n = document.createTreeWalker(
      t,
      NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT
    );
    for (; n.nextNode(); ) {
      const r = n.currentNode, s = r.nodeType === Node.TEXT_NODE ? r.textContent : r.innerHTML;
      if (Me(s)) {
        const i = r.nodeType === Node.TEXT_NODE ? r.parentElement : r;
        if (i) return i;
      }
    }
    return null;
  }
  async function De(t) {
    var l, R;
    const n = window.QwenPaw;
    if (!(n != null && n.host)) {
      console.warn("[a2a] QwenPaw.host not available");
      return;
    }
    const { getApiUrl: r, getApiToken: s } = n.host, i = r("/a2a/call/stream"), u = s();
    console.log("[a2a] Subscribing to SSE stream:", i);
    const a = document.createElement("div");
    a.style.cssText = "background:#f6ffed;border:1px solid #b7eb8f;border-radius:8px;padding:12px 16px;margin:4px 0;font-size:13px;white-space:pre-wrap;word-break:break-word;color:#262626;min-height:24px;", a.textContent = "正在连接远程 Agent...", t.textContent = "", t.appendChild(a);
    const p = new AbortController();
    try {
      const A = {
        Accept: "text/event-stream"
      };
      u && (A.Authorization = `Bearer ${u}`);
      try {
        const z = sessionStorage.getItem("qwenpaw-agent-storage") || localStorage.getItem("qwenpaw-agent-storage"), se = (R = (l = JSON.parse(z || "{}")) == null ? void 0 : l.state) == null ? void 0 : R.selectedAgent;
        se && (A["X-Agent-Id"] = se);
      } catch {
      }
      console.log("[a2a] Fetching SSE with headers:", A);
      const N = await fetch(i, { headers: A, signal: p.signal });
      if (console.log("[a2a] SSE response status:", N.status), !N.ok) {
        const z = await N.text().catch(() => "");
        a.textContent = `SSE 连接失败 (${N.status}): ${z.slice(
          0,
          100
        )}`, a.style.borderColor = "#ff4d4f", a.style.background = "#fff1f0";
        return;
      }
      if (!N.body) {
        a.textContent = "SSE 连接失败：无响应体", a.style.borderColor = "#ff4d4f", a.style.background = "#fff1f0";
        return;
      }
      const fe = N.body.getReader(), ee = new TextDecoder();
      let te = "";
      for (; ; ) {
        const { done: z, value: se } = await fe.read();
        if (z) {
          console.log("[a2a] SSE stream ended (done)");
          break;
        }
        te += ee.decode(se, { stream: !0 });
        const ne = te.split(`
`);
        te = ne.pop() || "";
        for (const C of ne)
          if (C.startsWith("data: "))
            try {
              const x = JSON.parse(C.slice(6));
              if (console.log("[a2a] SSE event:", x), x.done) {
                x.error && (a.textContent = `错误: ${x.error}`, a.style.borderColor = "#ff4d4f", a.style.background = "#fff1f0"), console.log("[a2a] SSE done signal received");
                return;
              }
              typeof x.response_text == "string" && x.response_text && (a.textContent = x.response_text);
            } catch (x) {
              console.warn("[a2a] SSE parse error:", x, "line:", C);
            }
      }
    } catch (A) {
      (A == null ? void 0 : A.name) !== "AbortError" && (console.error("[a2a] SSE subscription error:", A), a.textContent = `连接出错: ${(A == null ? void 0 : A.message) || A}`, a.style.borderColor = "#ff4d4f", a.style.background = "#fff1f0");
    }
  }
  function _t() {
    console.log("[a2a] Initializing stream interceptor");
    function t(i) {
      if (i.nodeType !== Node.ELEMENT_NODE) return;
      const u = i, a = Le(u);
      if (a && ve.has(a)) return;
      const p = It(u);
      p && (console.log("[a2a] Marker detected in DOM, msgId:", a), a && ve.add(a), De(p));
    }
    new MutationObserver((i) => {
      for (const u of i) {
        for (const a of u.addedNodes)
          t(a);
        u.target.nodeType === Node.ELEMENT_NODE && t(u.target);
      }
    }).observe(document.body, {
      childList: !0,
      subtree: !0,
      characterData: !0,
      characterDataOldValue: !0
    });
    const r = setInterval(() => {
      const i = document.evaluate(
        "//text()[contains(., 'A2A_STREAM_START')]",
        document.body,
        null,
        XPathResult.ORDERED_NODE_SNAPSHOT_TYPE,
        null
      );
      for (let u = 0; u < i.snapshotLength; u++) {
        const p = i.snapshotItem(u).parentElement;
        if (p) {
          const l = Le(p);
          if (l && ve.has(l)) continue;
          console.log("[a2a] Marker found in periodic scan, msgId:", l), l && ve.add(l), De(p);
        }
      }
    }, 500);
    window.addEventListener("beforeunload", () => clearInterval(r));
    const s = document.evaluate(
      "//text()[contains(., 'A2A_STREAM_START')]",
      document.body,
      null,
      XPathResult.ORDERED_NODE_SNAPSHOT_TYPE,
      null
    );
    for (let i = 0; i < s.snapshotLength; i++) {
      const a = s.snapshotItem(i).parentElement;
      if (a) {
        const p = Le(a);
        p && ve.add(p), console.log("[a2a] Marker found in existing DOM, msgId:", p), De(a);
      }
    }
  }
  (nt = (tt = window.QwenPaw).registerToolRender) == null || nt.call(tt, "cloudpaw", {
    proposal_choice: Et,
    a2a_call: kt
  }), (ot = (rt = window.QwenPaw).registerRoutes) == null || ot.call(rt, "cloudpaw", [
    {
      path: "/a2a",
      component: Tt,
      label: "A2A",
      icon: "🔗",
      priority: 10
    }
  ]), Nt(), Bt(), _t();
}
function Nt() {
  const e = "qwenpaw-last-used-agent", M = "qwenpaw-agent-storage", J = "cloudpaw-first-install", q = "cloud-orchestrator";
  if (localStorage.getItem(J)) return;
  localStorage.setItem(J, "true");
  function U() {
    localStorage.setItem(e, q);
    try {
      const F = localStorage.getItem(M);
      if (F) {
        const L = JSON.parse(F);
        L.state = L.state || {}, L.state.selectedAgent = q, localStorage.setItem(M, JSON.stringify(L));
      } else
        localStorage.setItem(
          M,
          JSON.stringify({
            version: 0,
            state: {
              selectedAgent: q,
              agents: [],
              lastChatIdByAgent: {}
            }
          })
        );
    } catch {
    }
    try {
      const F = sessionStorage.getItem(M);
      if (F) {
        const L = JSON.parse(F);
        L.state = L.state || {}, L.state.selectedAgent = q, sessionStorage.setItem(M, JSON.stringify(L));
      } else
        sessionStorage.setItem(
          M,
          JSON.stringify({
            version: 0,
            state: {
              selectedAgent: q,
              agents: [],
              lastChatIdByAgent: {}
            }
          })
        );
    } catch {
    }
  }
  U(), window.addEventListener(
    "beforeunload",
    () => {
      U();
    },
    { once: !0 }
  ), console.info(
    "[cloudpaw] Set default agent to cloud-orchestrator for first-time user"
  ), window.location.reload();
}
function Bt() {
  var W;
  const e = (W = window.QwenPaw) == null ? void 0 : W.modules;
  if (!e) return;
  const M = e["Chat/OptionsPanel/defaultConfig"];
  if (!(M != null && M.configProvider)) {
    console.warn(
      "[cloudpaw] configProvider not found — skipping welcome/theme patch"
    );
    return;
  }
  const J = M.configProvider, q = J.getConfig.bind(J), U = "https://gw.alicdn.com/imgextra/i2/O1CN01pyXzjQ1EL1PuZMlSd_!!6000000000334-2-tps-288-288.png", F = {
    zh: "CloudPaw 插件提示",
    en: "CloudPaw Plugin Tips",
    ja: "CloudPaw プラグインのヒント",
    ru: "Подсказки плагина CloudPaw"
  }, L = {
    zh: `告诉 CloudPaw 你想做什么，它会自动帮你完成云资源管理、基础设施编排与应用创建上云等任务。
⚠️ 使用前请在左上角下拉框切换到「CloudPaw-Master」，否则功能无法正常使用！
对于复杂的长程任务，建议使用 /mission 命令启动 Mission Mode 来自动拆解和执行。`,
    en: `Tell CloudPaw what you want to do — it will automatically handle cloud resource management, infrastructure orchestration, and application deployment.
⚠️ Please switch to 'CloudPaw-Master' from the dropdown in the top-left corner before use — features won't work otherwise!
For complex, multi-step tasks, use /mission to start Mission Mode for automated decomposition and execution.`,
    ja: `CloudPaw にやりたいことを伝えるだけで、クラウドリソース管理、インフラ構成、アプリケーションのデプロイなどを自動で行います。
⚠️ 使用前に左上のドロップダウンから「CloudPaw-Master」に切り替えてください。切り替えないと機能が正常に動作しません！
複雑なタスクには /mission コマンドで Mission Mode を起動し、自動分解・実行できます。`,
    ru: `Расскажите CloudPaw, что вы хотите сделать — он автоматически выполнит управление облачными ресурсами, оркестрацию инфраструктуры и развёртывание приложений.
⚠️ Перед началом переключитесь на 'CloudPaw-Master' в выпадающем списке в левом верхнем углу — иначе функции не будут работать!
Для сложных задач используйте /mission для автоматической декомпозиции и выполнения.`
  }, D = {
    zh: [
      {
        label: "创建个人主页并部署到云端",
        value: "/mission 帮我创建一个个人主页并上线到云端。页面包含：个人介绍、技能展示、项目经历、联系方式，所有个人信息请先用占位符代替。风格简洁清爽，适配手机和电脑。请使用阿里云 ECS 部署。"
      },
      {
        label: "快速发布 API 服务到云端",
        value: "/mission 帮我把一个 API 服务快速发布到云端。我希望默认提供 /health 和 /hello 两个接口，并给我可直接调用的地址和示例请求，配置尽量简单清晰。"
      }
    ],
    en: [
      {
        label: "Create a personal homepage and deploy to the cloud",
        value: "/mission Help me create a personal homepage and deploy it to the cloud. The page should include: personal introduction, skills, project experience, and contact info — please use placeholders for all personal information. The style should be clean and minimal, responsive for mobile and desktop. Please deploy using Alibaba Cloud ECS."
      },
      {
        label: "Deploy an API service to the cloud",
        value: "/mission Help me quickly deploy an API service to the cloud. I want it to provide /health and /hello endpoints by default, and give me a callable URL with example requests. Keep the configuration as simple and clean as possible."
      }
    ]
  };
  function Te() {
    const b = localStorage.getItem("language") || "";
    return b ? b.split("-")[0] : (navigator.language || "").split("-")[0] || "en";
  }
  if (J.getGreeting = () => F[Te()] || F.en, J.getDescription = () => L[Te()] || L.en, J.getPrompts = () => D[Te()] || D.en, J.getConfig = function(b) {
    var ke;
    const X = q(b);
    return {
      ...X,
      theme: {
        ...X.theme,
        leftHeader: {
          ...(ke = X.theme) == null ? void 0 : ke.leftHeader,
          title: "Work with CloudPaw"
        }
      },
      welcome: {
        ...X.welcome,
        avatar: U
      }
    };
  }, !document.getElementById("cloudpaw-welcome-style")) {
    const b = document.createElement("style");
    b.id = "cloudpaw-welcome-style", b.textContent = `
      [class*="chat-anywhere-welcome-default"] [class*="description"],
      [class*="message-list-welcome"] [class*="description"] {
        white-space: pre-line !important;
        text-align: center !important;
      }
    `, document.head.appendChild(b);
  }
  console.info("[cloudpaw] Patched welcome config & theme via configProvider");
}
Pt();
