function Bt() {
  var st, at, it, ct;
  const { React: e, antd: F, antdIcons: q, getApiUrl: X, getApiToken: K } = window.QwenPaw.host, {
    Card: G,
    Table: L,
    Tag: D,
    Typography: Ce,
    Space: J,
    Button: C,
    Input: Z,
    Radio: Te,
    Collapse: Wt,
    Descriptions: ae,
    Tooltip: Je,
    Spin: ge,
    message: Ue,
    theme: Ke
  } = F, { Text: Q } = Ce, { TextArea: ft } = Z, { useState: k, useMemo: ye, useCallback: R, useRef: Ft } = e, {
    InfoCircleOutlined: Re,
    DownOutlined: Ye,
    RightOutlined: mt,
    CheckCircleOutlined: ze,
    FieldTimeOutlined: Oe,
    FileTextOutlined: qe
  } = q || {};
  function Xe(t) {
    var a, d;
    const n = (d = (a = t == null ? void 0 : t.content) == null ? void 0 : a[0]) == null ? void 0 : d.data, r = n == null ? void 0 : n.arguments;
    if (typeof r == "string")
      try {
        return JSON.parse(r);
      } catch {
        return {};
      }
    return r ?? {};
  }
  function pt() {
    return window.currentSessionId ?? null;
  }
  function ie(t) {
    return typeof t == "string" ? t : t && typeof t == "object" && "text" in t ? t.text : String(t ?? "");
  }
  function gt(t) {
    if (t == null) return !0;
    const n = ie(t).trim();
    return !!(!n || /^[¥$]?0+(\.0+)?$/.test(n) || /^[-–—]+$/.test(n));
  }
  async function yt(t, n) {
    try {
      const r = K(), a = {
        "Content-Type": "application/json"
      };
      return r && (a.Authorization = `Bearer ${r}`), (await fetch(X("/interaction"), {
        method: "POST",
        headers: a,
        body: JSON.stringify({ session_id: t, result: n })
      })).ok;
    } catch {
      return !1;
    }
  }
  function Ge(t) {
    if (!t) return null;
    if (typeof t == "string")
      try {
        const n = JSON.parse(t);
        if (Array.isArray(n)) {
          const r = n.find(
            (a) => (a == null ? void 0 : a.type) === "text" && (a == null ? void 0 : a.text)
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
  function ht(t) {
    var l, i;
    if (!t || t.length < 2) return null;
    const n = (i = (l = t[1]) == null ? void 0 : l.data) == null ? void 0 : i.output, r = Ge(n);
    if (!r) return null;
    if (r.startsWith("Error:")) return r;
    const a = r.match(/^用户选择了「(.+?)」并确认部署$/);
    if (a) return `已确认部署「${a[1]}」`;
    const d = r.match(
      /^用户选择「(.+?)」并要求调整[：:](.+)$/
    );
    if (d)
      return `已选择「${d[1]}」并调整：${d[2]}`;
    if (r === "用户确认部署") return "已确认部署";
    const p = r.match(/^用户要求调整资源[：:](.+)$/);
    return p ? `已反馈调整意见：${p[1]}` : "已确认";
  }
  const Qe = [
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
  ], Et = new Set(
    Qe.map((t) => t.toLowerCase())
  );
  function De(t) {
    if (!Array.isArray(t) || t.length !== 10) return !1;
    const n = ie(t[0]).trim().toLowerCase();
    return Et.has(n);
  }
  function Ve(t) {
    if (!Array.isArray(t) || t.length !== 10) return !1;
    const n = ie(t[0]).trim();
    return /^(合计|总计|total)/i.test(n);
  }
  function xt(t) {
    const n = [];
    let r = [];
    for (const a of t)
      r.push(a), Ve(a) && (n.push(r), r = []);
    return r.length > 0 && (n.length > 0 ? n[n.length - 1].push(...r) : n.push(r)), n.length > 0 ? n : [t];
  }
  function wt(t) {
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
  function St({ data: t }) {
    var g, I, x;
    const [n, r] = k("confirm"), [a, d] = k(""), [p, l] = k(!1), [i, s] = k(null), [v, A] = k(
      {}
    ), _ = e.useRef(!1), U = e.useRef(null), [, oe] = k(0), B = t == null ? void 0 : t.content, H = B && B.length >= 2 && ((I = (g = B[1]) == null ? void 0 : g.data) == null ? void 0 : I.output), j = ye(
      () => ht(B),
      [B]
    ), O = _.current || H || j !== null, u = ye(() => {
      const h = Xe(t), f = h == null ? void 0 : h.data;
      if (!f) return null;
      try {
        const c = typeof f == "string" ? JSON.parse(f) : f;
        let b;
        if (h.strategy_names)
          try {
            const N = typeof h.strategy_names == "string" ? JSON.parse(h.strategy_names) : h.strategy_names;
            b = Array.isArray(N) ? N : [];
          } catch {
            b = [];
          }
        else c != null && c.proposal_names ? b = c.proposal_names : b = [];
        const Y = b.length >= 2 ? b.length : 0;
        let $;
        if (Array.isArray(c) && c.length > 0)
          if (Array.isArray(c[0]) && c[0].length === 10 && !Array.isArray(c[0][0])) {
            const z = c.filter(
              (se) => !De(se)
            );
            if (z.filter(
              (se) => Ve(se)
            ).length >= 2)
              $ = xt(z);
            else if (Y >= 2 && z.length >= Y * 2) {
              const se = Math.ceil(z.length / Y);
              $ = [];
              for (let pe = 0; pe < z.length; pe += se)
                $.push(z.slice(pe, pe + se));
            } else
              $ = [z];
          } else
            $ = c.map(
              (z) => z.filter(
                (me) => Array.isArray(me) && me.length === 10 && !De(me)
              )
            );
        else if (c != null && c.proposals)
          $ = c.proposals.map(
            (N) => N.filter((z) => !De(z))
          );
        else
          return null;
        if ($ = $.filter((N) => N.length > 0), $.length === 0) return null;
        const Se = ["方案一", "方案二", "方案三", "方案四", "方案五"];
        if (b.length < $.length)
          for (let N = b.length; N < $.length; N++)
            b.push(Se[N] || `方案${N + 1}`);
        return { proposals: $, names: b };
      } catch {
        return null;
      }
    }, [t]), E = pt(), m = (((x = u == null ? void 0 : u.proposals) == null ? void 0 : x.length) ?? 0) > 1, P = R(async () => {
      if (!E || O || !u) return;
      const h = m ? i : 0, f = u.names[h ?? 0] || `方案${(h ?? 0) + 1}`;
      let c;
      n === "confirm" ? c = `用户选择了「${f}」并确认部署` : c = `用户选择「${f}」并要求调整：${a.trim() || "未填写具体要求"}`, l(!0);
      const b = await yt(E, c);
      l(!1), b ? (_.current = !0, n === "confirm" ? U.current = `已确认部署「${f}」` : U.current = `已选择「${f}」并调整：${a.trim()}`, oe((Y) => Y + 1), Ue.success(
        n === "confirm" ? "已确认部署方案" : "已提交调整意见"
      )) : Ue.error("操作失败，请重试");
    }, [
      E,
      O,
      u,
      n,
      a,
      i,
      m
    ]), xe = (t == null ? void 0 : t.status) === "in_progress" || (t == null ? void 0 : t.status) === "created";
    if (!u)
      return xe ? e.createElement(
        "div",
        {
          style: {
            width: "100%",
            borderRadius: 10,
            border: "1px solid #f0f0f0",
            background: "#fff",
            padding: "24px 16px",
            margin: "4px 0",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 12
          }
        },
        e.createElement(ge, { size: "default" }),
        e.createElement(
          Q,
          { type: "secondary", style: { fontSize: 13 } },
          "正在生成资源方案..."
        )
      ) : e.createElement(
        G,
        { size: "small", style: { margin: "4px 0" } },
        e.createElement(Q, { type: "secondary" }, "无法解析方案数据")
      );
    const { proposals: ee, names: ue } = u, W = Qe.map((h, f) => ({
      title: h,
      dataIndex: `col_${f}`,
      key: `col_${f}`,
      render: (c) => wt(c),
      ellipsis: f < 3
    }));
    let fe = "待确认", te = "processing";
    O && (te = "success", fe = U.current || j || "已确认");
    const le = e.createElement(
      D,
      {
        color: te,
        style: { marginLeft: 4 }
      },
      fe
    ), we = e.createElement(
      J,
      { size: 8 },
      e.createElement("span", null, "☁️"),
      e.createElement(
        Q,
        { strong: !0, style: { fontSize: 14 } },
        O ? "资源配置方案" : "请确认您的资源配置方案"
      ),
      le
    ), de = ee.map((h, f) => {
      const c = m ? i === f : !0, b = v[f] || !1, Y = (T) => {
        const re = ie(T[0] || "").trim();
        return /^合计|^总计|^total/i.test(re);
      }, $ = h.find(Y), Se = h.filter((T) => !Y(T)), N = Se.map((T) => ({
        type: ie(T[0] || ""),
        purpose: ie(T[1] || ""),
        spec: ie(T[2] || ""),
        cost: T[9] ?? null
      })), z = $ ? ie($[9] ?? "") : "", me = h.map((T, re) => {
        const Ae = { key: re };
        return T.forEach((He, je) => {
          Ae[`col_${je}`] = He;
        }), Ae;
      }), se = c ? "2px solid #1677ff" : "1px solid #e8e8e8", pe = c ? "0 0 0 2px #e6f4ff" : "none";
      return e.createElement(
        "div",
        {
          key: f,
          style: {
            flex: 1,
            minWidth: 240,
            border: se,
            borderRadius: 8,
            cursor: m ? "pointer" : "default",
            transition: "all 0.2s ease",
            boxShadow: pe,
            background: "#fff"
          },
          onClick: m ? () => s(f) : void 0
        },
        e.createElement(
          "div",
          { style: { padding: "10px 12px" } },
          // Proposal name
          e.createElement(
            Q,
            {
              strong: !0,
              style: { fontSize: 14, display: "block", marginBottom: 8 }
            },
            ue[f]
          ),
          ...N.map(
            (T, re) => e.createElement(
              "div",
              {
                key: re,
                style: {
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  padding: "4px 0",
                  borderBottom: re < N.length - 1 ? "1px solid #f5f5f5" : "none"
                }
              },
              e.createElement(
                "div",
                { style: { flex: 1, minWidth: 0 } },
                e.createElement(
                  "span",
                  { style: { fontSize: 12, color: "#262626" } },
                  T.type
                ),
                T.spec && e.createElement(
                  "span",
                  {
                    style: { fontSize: 11, color: "#8c8c8c", marginLeft: 6 }
                  },
                  T.spec
                )
              ),
              !gt(T.cost) && e.createElement(
                "span",
                {
                  style: {
                    fontSize: 12,
                    color: "#595959",
                    flexShrink: 0,
                    marginLeft: 8
                  }
                },
                ie(T.cost)
              )
            )
          ),
          // Total cost
          z && e.createElement(
            "div",
            {
              style: {
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginTop: 6,
                paddingTop: 6,
                borderTop: "1px dashed #e8e8e8"
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
              z
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
                color: "#8c8c8c",
                fontSize: 12,
                cursor: "pointer",
                marginTop: 6
              },
              onClick: (T) => {
                T.stopPropagation(), A((re) => ({
                  ...re,
                  [f]: !re[f]
                }));
              }
            },
            e.createElement(
              b && Ye ? Ye : mt || "span",
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
          b && e.createElement(
            "div",
            {
              onClick: (T) => T.stopPropagation(),
              style: { marginTop: 4, maxHeight: 260, overflow: "auto" }
            },
            e.createElement(L, {
              columns: W,
              dataSource: me,
              pagination: !1,
              size: "small",
              scroll: { x: "max-content" }
            })
          )
        )
      );
    }), ne = e.createElement(
      "div",
      {
        style: {
          background: "#fffbe6",
          border: "1px solid #ffe58f",
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
          color: "#faad14",
          fontSize: 14,
          flexShrink: 0,
          marginTop: 1
        }
      }) : e.createElement("span", null, "⚠️"),
      e.createElement(
        "span",
        {
          style: { fontSize: 12, color: "#8c6e00", lineHeight: 1.5 }
        },
        "在服务部署与配置过程中，可能因实际资源需求变化导致资源变配及费用调整，请及时关注实际资源使用情况与账单详情。"
      )
    ), M = !O && E && !(m && i === null) && e.createElement(
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
              border: `1px solid ${n === "confirm" ? "#1677ff" : "#e8e8e8"}`,
              borderRadius: 6,
              padding: "8px 12px",
              cursor: "pointer",
              transition: "all 0.15s ease",
              display: "flex",
              alignItems: "center",
              gap: 8,
              background: n === "confirm" ? "#e6f4ff" : "transparent"
            },
            onClick: () => r("confirm")
          },
          e.createElement(Te, { checked: n === "confirm" }),
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
              border: `1px solid ${n === "adjust" ? "#1677ff" : "#e8e8e8"}`,
              borderRadius: 6,
              padding: "8px 12px",
              transition: "all 0.15s ease",
              background: n === "adjust" ? "#e6f4ff" : "transparent"
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
              onClick: () => r("adjust")
            },
            e.createElement(Te, { checked: n === "adjust" }),
            e.createElement(
              "span",
              { style: { fontSize: 13 } },
              "调整资源"
            )
          ),
          n === "adjust" && e.createElement(ft, {
            value: a,
            onChange: (h) => d(h.target.value),
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
          Q,
          { type: "secondary", style: { fontSize: 11 } },
          m ? "一小时后未操作将自动选择第一个方案" : "一小时后未操作将自动确认部署"
        ),
        e.createElement(
          C,
          {
            type: "primary",
            size: "small",
            loading: p,
            onClick: P,
            disabled: n === "adjust" && !a.trim()
          },
          n === "confirm" ? "确认部署" : "提交调整"
        )
      )
    ), w = m && i === null && !O && e.createElement(
      "div",
      {
        style: {
          textAlign: "center",
          padding: "8px 0 4px",
          color: "rgba(0,0,0,0.45)",
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
          border: "1px solid #f0f0f0",
          overflow: "hidden",
          background: "#fff",
          padding: "12px 16px",
          margin: "4px 0"
        }
      },
      // Header
      e.createElement("div", { style: { marginBottom: 10 } }, we),
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
        ...de
      ),
      w,
      ne,
      !O && M
    );
  }
  function At({ data: t }) {
    const [n, r] = k(null), [a, d] = k(!1), p = (t == null ? void 0 : t.status) === "in_progress" || (t == null ? void 0 : t.status) === "created", l = ye(() => {
      const u = Xe(t);
      return (u == null ? void 0 : u.loop_dir) || null;
    }, [t]), i = ye(() => {
      var E, m, P;
      const u = Ge((P = (m = (E = t == null ? void 0 : t.content) == null ? void 0 : E[1]) == null ? void 0 : m.data) == null ? void 0 : P.output);
      if (!u) return null;
      try {
        return JSON.parse(u);
      } catch {
        return null;
      }
    }, [t]), s = (i == null ? void 0 : i.status) === "ok", v = (i == null ? void 0 : i.status) === "error", A = v ? (i == null ? void 0 : i.message) || "未知错误" : null, _ = R(async () => {
      if (l)
        try {
          const u = K(), E = {};
          u && (E.Authorization = `Bearer ${u}`);
          const m = await fetch(
            X(`/prd?loop_dir=${encodeURIComponent(l)}`),
            { headers: E }
          );
          if (!m.ok) {
            d(!0);
            return;
          }
          const P = await m.json();
          P && Array.isArray(P.userStories) ? (r(P), d(!1)) : d(!0);
        } catch {
          d(!0);
        }
    }, [l]);
    if (e.useEffect(() => {
      !p && s && l && _();
    }, [p, s, l, _]), p)
      return e.createElement(
        "div",
        {
          style: {
            width: "100%",
            borderRadius: 10,
            border: "1px solid #f0f0f0",
            background: "#fff",
            padding: "24px 16px",
            margin: "4px 0",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 12
          }
        },
        e.createElement(ge, { size: "default" }),
        e.createElement(
          Q,
          { type: "secondary", style: { fontSize: 13 } },
          "正在更新 PRD..."
        )
      );
    if (v)
      return e.createElement(
        "div",
        {
          style: {
            width: "100%",
            borderRadius: 10,
            border: "1px solid #fff1f0",
            background: "#fff1f0",
            padding: "12px 16px",
            margin: "4px 0",
            display: "flex",
            alignItems: "center",
            gap: 8
          }
        },
        e.createElement(
          Q,
          { type: "danger", style: { fontSize: 13 } },
          `PRD 格式错误，将会修正：${A}`
        )
      );
    if (!s || a || !n) return null;
    const U = n.userStories, oe = [...U].sort(
      (u, E) => (u.priority || 99) - (E.priority || 99)
    ), B = U.filter((u) => u.passes).length, H = [
      {
        title: "状态",
        key: "status",
        width: 50,
        align: "center",
        render: (u, E) => {
          if (E.passes) {
            const P = ze ? e.createElement(ze, {
              style: { color: "#52c41a", fontSize: 18 }
            }) : "✅";
            return e.createElement(Je, { title: "已完成" }, P);
          }
          const m = Oe ? e.createElement(Oe, {
            style: { color: "#faad14", fontSize: 18 }
          }) : "🕐";
          return e.createElement(Je, { title: "待处理" }, m);
        }
      },
      {
        title: "ID",
        dataIndex: "id",
        key: "id",
        width: 85,
        render: (u) => e.createElement(D, { color: "blue" }, u)
      },
      {
        title: "标题",
        dataIndex: "title",
        key: "title",
        render: (u) => e.createElement(Q, { strong: !0 }, u)
      },
      {
        title: "优先级",
        key: "priority",
        width: 70,
        render: (u, E) => {
          const m = E.priority;
          return e.createElement(
            D,
            { color: "default" },
            m != null ? String(m) : "-"
          );
        }
      },
      {
        title: "描述",
        dataIndex: "description",
        key: "description",
        ellipsis: !0
      },
      {
        title: "验收标准",
        key: "acceptance",
        width: 200,
        render: (u, E) => {
          const m = E.acceptanceCriteria;
          return typeof m == "string" ? e.createElement(
            "div",
            {
              style: { fontSize: 12, color: "#666", whiteSpace: "pre-wrap" }
            },
            m.length > 100 ? m.slice(0, 100) + "..." : m
          ) : Array.isArray(m) ? e.createElement(
            "div",
            { style: { fontSize: 12, color: "#666" } },
            m.length > 2 ? m.slice(0, 2).join(", ") + "..." : m.join(", ")
          ) : "-";
        }
      }
    ], j = e.createElement(
      J,
      { size: 8 },
      qe ? e.createElement(qe, { style: { color: "#1677ff" } }) : null,
      e.createElement(
        "span",
        { style: { fontSize: 14 } },
        e.createElement(Q, { strong: !0 }, n.project || "PRD")
      )
    ), O = e.createElement(L, {
      columns: H,
      dataSource: oe.map((u) => ({ ...u, key: u.id })),
      size: "small",
      pagination: !1,
      scroll: { x: "max-content" },
      style: { marginBottom: 4 }
    });
    return e.createElement(
      "div",
      {
        style: {
          width: "100%",
          borderRadius: 10,
          border: "1px solid #f0f0f0",
          overflow: "hidden",
          background: "#fff",
          padding: "12px 16px",
          margin: "4px 0"
        }
      },
      e.createElement("div", { style: { marginBottom: 8 } }, j),
      e.createElement(ae, {
        size: "small",
        column: { xs: 1, sm: 2, md: 3 },
        style: { marginBottom: 12 },
        bordered: !1,
        items: [
          {
            key: "progress",
            label: "进度",
            children: `${B}/${U.length} 完成`
          }
        ]
      }),
      O,
      e.createElement(
        "div",
        {
          style: {
            fontSize: 11,
            color: "#8c8c8c",
            display: "flex",
            alignItems: "center",
            gap: 8
          }
        },
        ze ? e.createElement(ze, {
          style: { color: "#52c41a", fontSize: 14 }
        }) : "✅",
        e.createElement("span", null, "已完成"),
        e.createElement("span", { style: { margin: "0 4px" } }, "·"),
        Oe ? e.createElement(Oe, {
          style: { color: "#faad14", fontSize: 14 }
        }) : "🕐",
        e.createElement("span", null, "待处理")
      )
    );
  }
  const {
    Form: ce,
    Select: Pe,
    Drawer: bt,
    Modal: Ze,
    Empty: kt,
    Badge: et,
    Divider: Ct,
    message: V
  } = F, {
    ApiOutlined: tt,
    PlusOutlined: nt,
    ReloadOutlined: $e,
    DeleteOutlined: rt,
    LinkOutlined: ot,
    DisconnectOutlined: Jt
  } = q || {}, { useEffect: lt } = e, he = "/a2a/agents";
  function Ne() {
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
  async function Ee(t, n) {
    const r = X(t), a = K == null ? void 0 : K(), d = Ne(), p = {
      "Content-Type": "application/json",
      ...a ? { Authorization: `Bearer ${a}` } : {},
      ...d ? { "X-Agent-Id": d } : {}
    }, l = await fetch(r, {
      ...n,
      headers: { ...p, ...(n == null ? void 0 : n.headers) || {} }
    });
    if (!l.ok) {
      const i = await l.text().catch(() => "");
      throw new Error(i || `HTTP ${l.status}`);
    }
    return l.status === 204 || l.headers.get("content-length") === "0" ? null : l.json();
  }
  function Tt(t) {
    var i;
    const { agent: n, onClick: r } = t, a = n.status === "connected", d = a ? "#52c41a" : n.status === "error" ? "#ff4d4f" : "#d9d9d9", p = a ? "已连接" : n.status === "error" ? "错误" : "未连接", l = {
      gateway: "阿里云Agent Hub",
      bearer: "Bearer Token",
      api_key: "API Key"
    };
    return e.createElement(
      G,
      {
        hoverable: !0,
        onClick: r,
        size: "small",
        style: { cursor: "pointer" },
        title: e.createElement(
          J,
          null,
          e.createElement(et, { color: d }),
          e.createElement(
            "span",
            null,
            n.name || n.alias || n.url
          )
        ),
        extra: n.auth_type ? e.createElement(
          D,
          { color: "blue" },
          l[n.auth_type] || n.auth_type
        ) : null
      },
      e.createElement(
        "div",
        { style: { fontSize: 12, color: "#666" } },
        e.createElement(
          "div",
          { style: { marginBottom: 4 } },
          ot ? e.createElement(ot, { style: { marginRight: 4 } }) : null,
          n.url
        ),
        n.description ? e.createElement(
          "div",
          { style: { marginBottom: 4, color: "#999" } },
          n.description
        ) : null,
        ((i = n.skills) == null ? void 0 : i.length) > 0 ? e.createElement(
          "div",
          null,
          n.skills.slice(0, 3).map(
            (s, v) => e.createElement(
              D,
              { key: v, style: { fontSize: 11 } },
              s.name
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
          { style: { marginTop: 4, color: d, fontSize: 11 } },
          p,
          n.error ? ` - ${n.error}` : ""
        )
      )
    );
  }
  function vt() {
    const t = e.useRef(Ne()), [n, r] = k(t.current);
    return lt(() => {
      const a = () => {
        const p = Ne();
        p !== t.current && (t.current = p, r(p));
      }, d = setInterval(a, 200);
      return window.addEventListener("storage", a), () => {
        clearInterval(d), window.removeEventListener("storage", a);
      };
    }, []), n;
  }
  function It() {
    var dt, ut;
    const { token: t } = Ke.useToken(), n = vt(), [r, a] = k([]), [d, p] = k(!0), [l, i] = k(!1), [s, v] = k(null), [A, _] = k(!1), [U, oe] = k(!1), [B, H] = k(!1), [j, O] = k(!1), [u, E] = k(""), [m] = ce.useForm(), [P, xe] = k(!1), [ee, ue] = k(!1), [W, fe] = k([]), [te, le] = k(
      /* @__PURE__ */ new Set()
    ), [we, de] = k(
      []
    ), ne = e.useRef(null), M = ye(
      () => new Set(r.map((o) => o.url)),
      [r]
    ), w = e.useRef(M);
    w.current = M;
    const g = R(async () => {
      p(!0);
      try {
        const o = await Ee(he);
        a((o == null ? void 0 : o.agents) || []);
      } catch {
        a([]);
      } finally {
        p(!1);
      }
    }, []);
    lt(() => {
      g();
    }, [n]);
    const I = R(() => {
      _(!0), v(null), i(!0), m.resetFields(), m.setFieldsValue({
        url: "",
        alias: "",
        auth_type: "",
        auth_token: ""
      });
    }, [m]), x = R((o) => {
      _(!1), v(o), i(!0);
    }, []), h = R(() => {
      O(!1), E("");
    }, []), f = R(async () => {
      if (!s || !u.trim()) return;
      const o = s.alias || s.url;
      if (u.trim() === o) {
        h();
        return;
      }
      try {
        const y = await Ee(
          `${he}?alias=${encodeURIComponent(o)}`,
          {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ new_alias: u.trim() })
          }
        );
        V.success("别名已修改"), O(!1), v(y), await g();
      } catch (y) {
        V.error(y.message || "修改失败");
      }
    }, [s, u, g, h]), c = R(() => {
      h(), i(!1), v(null), _(!1), m.resetFields();
    }, [h, m]), b = R(async () => {
      let o;
      try {
        o = await m.validateFields();
      } catch {
        return;
      }
      const y = {
        url: String(o.url || "").trim(),
        alias: String(o.alias || "").trim() || void 0,
        auth_type: String(o.auth_type || ""),
        auth_token: String(o.auth_token || "")
      };
      if (y.url) {
        oe(!0);
        try {
          await Ee(he, {
            method: "POST",
            body: JSON.stringify(y)
          }), V.success("A2A Agent 注册成功"), await g(), c();
        } catch (S) {
          V.error(S.message || "注册失败");
        } finally {
          oe(!1);
        }
      }
    }, [m, g, c]), Y = R(async () => {
      if (!s) return;
      const o = s.alias || s.url, y = s.name || o;
      Ze.confirm({
        title: "确认删除",
        content: `确定删除 A2A Agent「${y}」吗？此操作不可撤销。`,
        okText: "删除",
        cancelText: "取消",
        okButtonProps: { danger: !0 },
        async onOk() {
          try {
            await Ee(`${he}?alias=${encodeURIComponent(o)}`, {
              method: "DELETE"
            }), V.success(`已删除 A2A Agent「${y}」`), await g(), c();
          } catch (S) {
            V.error(S.message || "删除失败");
          }
        }
      });
    }, [s, g, c]), $ = R(async () => {
      if (!s) return;
      const o = s.alias || s.url;
      H(!0);
      try {
        const y = await Ee(
          `${he}/refresh?alias=${encodeURIComponent(o)}`,
          {
            method: "POST"
          }
        );
        V.success("Agent Card 已刷新"), await g(), y && v(y);
      } catch (y) {
        V.error(y.message || "刷新失败");
      } finally {
        H(!1);
      }
    }, [s, g]), Se = R(() => {
      s && (E(s.alias || ""), O(!0));
    }, [s]), N = R(() => {
      xe(!0), fe([]), le(/* @__PURE__ */ new Set()), de([]), ne.current = null, me();
    }, []), z = R(() => {
      ee && ne.current && ne.current.abort(), xe(!1), fe([]), le(/* @__PURE__ */ new Set()), de([]), ne.current = null;
    }, [ee]), me = R(async () => {
      ue(!0);
      const o = new AbortController();
      ne.current = o;
      try {
        const y = K == null ? void 0 : K(), S = Ne(), Ie = {
          ...y ? { Authorization: `Bearer ${y}` } : {},
          ...S ? { "X-Agent-Id": S } : {}
        }, ke = await fetch(X("/a2a/import"), {
          method: "GET",
          headers: Ie,
          signal: o.signal
        });
        if (!ke.ok) {
          const _e = await ke.text().catch(() => "");
          throw new Error(_e || `HTTP ${ke.status}`);
        }
        const We = await ke.json(), Fe = (We == null ? void 0 : We.agents) || [];
        if (Fe.length === 0) {
          V.warning("未找到可用的 Agent");
          return;
        }
        fe(Fe);
        const Lt = w.current;
        le(
          new Set(
            Fe.filter((_e) => !Lt.has(_e.url)).map((_e) => _e.url)
          )
        );
      } catch (y) {
        if ((y == null ? void 0 : y.name) === "AbortError") return;
        V.error(y.message || "获取 Agent 列表失败");
      } finally {
        ue(!1), ne.current = null;
      }
    }, []), se = R((o) => {
      le((y) => {
        const S = new Set(y);
        return S.has(o) ? S.delete(o) : S.add(o), S;
      });
    }, []), pe = R(() => {
      le(
        new Set(
          W.filter((o) => !M.has(o.url)).map((o) => o.url)
        )
      );
    }, [W, M]), T = R(() => {
      le(/* @__PURE__ */ new Set());
    }, []), re = R(async () => {
      const o = W.filter(
        (S) => te.has(S.url) && !M.has(S.url)
      );
      if (o.length === 0) {
        V.warning("请至少选择一个 Agent");
        return;
      }
      ue(!0), de([]);
      const y = [];
      for (const S of o) {
        try {
          await Ee(he, {
            method: "POST",
            body: JSON.stringify({
              url: S.url,
              alias: S.name || void 0,
              auth_type: S.auth_type || "gateway",
              auth_token: ""
            })
          }), y.push({ name: S.name || S.url, success: !0 });
        } catch (Ie) {
          y.push({
            name: S.name || S.url,
            success: !1,
            error: Ie.message || "注册失败"
          });
        }
        de([...y]);
      }
      await g(), V.success(
        `导入完成：成功 ${y.filter((S) => S.success).length} 个，失败 ${y.filter((S) => !S.success).length} 个`
      ), ue(!1), setTimeout(() => z(), 800);
    }, [W, te, g, M]), Ae = ((dt = ce.useWatch) == null ? void 0 : dt.call(ce, "auth_type", m)) ?? "", He = e.createElement(
      ce,
      { form: m, layout: "vertical" },
      e.createElement(
        ce.Item,
        {
          name: "url",
          label: "Agent URL",
          rules: [{ required: !0, message: "请输入 Agent URL" }]
        },
        e.createElement(Z, {
          placeholder: "https://agent.example.com"
        })
      ),
      e.createElement(
        ce.Item,
        { name: "alias", label: "别名" },
        e.createElement(Z, { placeholder: "输入别名（可选）" })
      ),
      e.createElement(
        ce.Item,
        { name: "auth_type", label: "认证类型" },
        e.createElement(
          Pe,
          { allowClear: !0, placeholder: "无认证" },
          e.createElement(
            Pe.Option,
            { value: "bearer" },
            "Bearer Token"
          ),
          e.createElement(Pe.Option, { value: "api_key" }, "API Key"),
          e.createElement(
            Pe.Option,
            { value: "gateway" },
            "阿里云Agent Hub"
          )
        )
      ),
      Ae === "gateway" ? e.createElement(
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
      Ae && Ae !== "gateway" ? e.createElement(
        ce.Item,
        { name: "auth_token", label: "认证凭证" },
        e.createElement(Z.Password, {
          placeholder: "Bearer Token 或 API Key"
        })
      ) : null
    ), je = s ? e.createElement(
      "div",
      null,
      e.createElement(
        ae,
        { column: 1, bordered: !0, size: "small" },
        e.createElement(
          ae.Item,
          { label: "URL" },
          s.url
        ),
        e.createElement(
          ae.Item,
          { label: "别名" },
          j ? e.createElement(
            "div",
            {
              style: { display: "flex", alignItems: "center", gap: 6 }
            },
            e.createElement(Z, {
              value: u,
              onChange: (o) => E(o.target.value),
              onPressEnter: f,
              autoFocus: !0,
              placeholder: "输入新别名",
              size: "small",
              style: { flex: 1 }
            }),
            e.createElement(
              C,
              {
                type: "link",
                size: "small",
                onClick: f,
                disabled: !u.trim(),
                style: { padding: 0 }
              },
              "保存"
            )
          ) : e.createElement(
            "div",
            {
              style: { display: "flex", alignItems: "center", gap: 8 }
            },
            e.createElement("span", null, s.alias || "-"),
            e.createElement(
              "a",
              {
                style: { fontSize: 12 },
                onClick: Se
              },
              "修改"
            )
          )
        ),
        e.createElement(
          ae.Item,
          { label: "Agent 名称" },
          s.name || "-"
        ),
        e.createElement(
          ae.Item,
          { label: "状态" },
          e.createElement(et, {
            color: s.status === "connected" ? "#52c41a" : s.status === "error" ? "#ff4d4f" : "#d9d9d9",
            text: s.status === "connected" ? "已连接" : s.status === "error" ? "错误" : "未连接"
          })
        ),
        e.createElement(
          ae.Item,
          { label: "认证类型" },
          s.auth_type ? e.createElement(
            D,
            { color: "blue" },
            {
              gateway: "阿里云Agent Hub",
              bearer: "Bearer Token",
              api_key: "API Key"
            }[s.auth_type] || s.auth_type
          ) : "无认证"
        ),
        e.createElement(
          ae.Item,
          { label: "描述" },
          s.description || "-"
        ),
        e.createElement(
          ae.Item,
          { label: "版本" },
          s.version || "-"
        )
      ),
      ((ut = s.skills) == null ? void 0 : ut.length) > 0 ? e.createElement(
        "div",
        { style: { marginTop: 16 } },
        e.createElement("h4", null, "技能"),
        ...s.skills.map(
          (o, y) => e.createElement(
            G,
            { key: y, size: "small", style: { marginBottom: 8 } },
            e.createElement("strong", null, o.name),
            o.description ? e.createElement(
              "div",
              { style: { color: "#666", fontSize: 12 } },
              o.description
            ) : null
          )
        )
      ) : null,
      s.capabilities ? e.createElement(
        "div",
        { style: { marginTop: 16 } },
        e.createElement("h4", null, "能力"),
        e.createElement(
          J,
          null,
          e.createElement(
            D,
            {
              color: s.capabilities.streaming ? "green" : "default"
            },
            "Streaming"
          ),
          e.createElement(
            D,
            {
              color: s.capabilities.push_notifications ? "green" : "default"
            },
            "Push Notifications"
          )
        )
      ) : null,
      s.error ? e.createElement(
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
        s.error
      ) : null,
      e.createElement(Ct, null),
      e.createElement(
        J,
        null,
        e.createElement(
          C,
          {
            type: "primary",
            icon: $e ? e.createElement($e) : null,
            loading: B,
            onClick: $
          },
          "刷新 Agent Card"
        ),
        e.createElement(
          C,
          {
            danger: !0,
            icon: rt ? e.createElement(rt) : null,
            onClick: Y
          },
          "删除"
        )
      )
    ) : null, $t = e.createElement(
      bt,
      {
        title: A ? "注册远程 A2A Agent" : (s == null ? void 0 : s.name) || (s == null ? void 0 : s.alias) || "Agent 详情",
        open: l,
        onClose: c,
        width: 480,
        footer: A ? e.createElement(
          J,
          { style: { display: "flex", justifyContent: "flex-end" } },
          e.createElement(C, { onClick: c }, "取消"),
          e.createElement(
            C,
            { type: "primary", loading: U, onClick: b },
            "注册"
          )
        ) : null
      },
      A ? He : je
    ), Nt = e.createElement(
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
          J,
          null,
          e.createElement(
            C,
            {
              icon: $e ? e.createElement($e) : null,
              onClick: g,
              loading: d
            },
            "刷新列表"
          ),
          e.createElement(
            C,
            {
              icon: tt ? e.createElement(tt) : null,
              onClick: N
            },
            "从阿里云AgentHub导入"
          ),
          e.createElement(
            C,
            {
              type: "primary",
              icon: nt ? e.createElement(nt) : null,
              onClick: I
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
    ), Dt = d ? e.createElement(
      "div",
      { style: { textAlign: "center", padding: 60 } },
      e.createElement(ge, { size: "large" })
    ) : r.length === 0 ? e.createElement(kt, {
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
        (o) => e.createElement(Tt, {
          key: o.alias || o.url,
          agent: o,
          onClick: () => x(o)
        })
      )
    ), be = we.length > 0, Mt = e.createElement(
      Ze,
      {
        title: be ? "导入结果" : "从阿里云AgentHub导入 Agent",
        open: P,
        onCancel: z,
        closable: !ee || be,
        maskClosable: !ee || be,
        width: 800,
        footer: be ? e.createElement(
          J,
          { style: { display: "flex", justifyContent: "flex-end" } },
          e.createElement(
            C,
            { type: "primary", onClick: z },
            "关闭"
          )
        ) : W.length > 0 ? e.createElement(
          J,
          { style: { display: "flex", justifyContent: "flex-end" } },
          e.createElement(
            C,
            { onClick: z },
            "取消"
          ),
          e.createElement(
            C,
            {
              type: "primary",
              loading: ee,
              disabled: te.size === 0,
              onClick: re
            },
            `确认导入 (${te.size}/${W.length})`
          )
        ) : null
      },
      // Loading state
      ee && W.length === 0 && e.createElement(
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
        e.createElement(ge, { size: "large" }),
        e.createElement(
          "span",
          { style: { fontSize: 13, color: t.colorTextTertiary } },
          "正在从 AgentHub 获取 Agent 列表..."
        )
      ),
      // Agent selection list (hide after import completed)
      !ee && !be && W.length > 0 && e.createElement(
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
            `共 ${W.length} 个 Agent，已选 ${te.size} 个`
          ),
          e.createElement(
            J,
            { size: 4 },
            e.createElement(
              C,
              {
                size: "small",
                type: "link",
                style: { padding: 0, height: "auto" },
                onClick: pe
              },
              "全选"
            ),
            e.createElement(
              C,
              {
                size: "small",
                type: "link",
                style: { padding: 0, height: "auto" },
                onClick: T
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
          ...W.map((o) => {
            var S;
            const y = te.has(o.url);
            return e.createElement(
              "div",
              {
                key: o.url,
                style: {
                  display: "flex",
                  gap: 8,
                  padding: 10,
                  border: y ? `1px solid ${t.colorInfo}` : `1px solid ${t.colorBorderSecondary}`,
                  borderRadius: 6,
                  cursor: M.has(o.url) ? "default" : "pointer",
                  background: M.has(o.url) ? t.colorBgLayout : y ? t.colorInfoBg : t.colorBgContainer,
                  transition: "all 0.15s ease",
                  opacity: M.has(o.url) ? 0.7 : 1
                },
                onClick: () => {
                  M.has(o.url) || se(o.url);
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
                ((S = o.skills) == null ? void 0 : S.length) > 0 ? e.createElement(
                  "div",
                  { style: { marginTop: 4 } },
                  ...o.skills.slice(0, 3).map(
                    (Ie, ke) => e.createElement(
                      D,
                      {
                        key: ke,
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
              M.has(o.url) ? e.createElement(
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
      be && e.createElement(
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
        ...we.map(
          (o, y) => e.createElement(
            "div",
            {
              key: y,
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
      Nt,
      Dt,
      $t,
      Mt
    );
  }
  function _t({ data: t }) {
    var de, ne, M;
    const { token: n } = Ke.useToken(), r = e.useRef(null), [a, d] = k({}), p = ye(() => {
      var g, I, x;
      const w = (x = (I = (g = t == null ? void 0 : t.content) == null ? void 0 : g[0]) == null ? void 0 : I.data) == null ? void 0 : x.arguments;
      if (!w) return null;
      try {
        return JSON.parse(w);
      } catch {
        return null;
      }
    }, [(M = (ne = (de = t == null ? void 0 : t.content) == null ? void 0 : de[0]) == null ? void 0 : ne.data) == null ? void 0 : M.arguments]), { toolResult: l, rawErrorText: i } = ye(() => {
      var g;
      const w = t == null ? void 0 : t.content;
      if (!Array.isArray(w))
        return { toolResult: null, rawErrorText: "" };
      for (const I of w) {
        const x = (g = I == null ? void 0 : I.data) == null ? void 0 : g.output;
        if (!x) continue;
        let h = "";
        if (Array.isArray(x)) {
          const f = x.find(
            (c) => (c == null ? void 0 : c.type) === "text" && (c == null ? void 0 : c.text)
          );
          h = (f == null ? void 0 : f.text) || "";
        } else if (typeof x == "string")
          try {
            const f = JSON.parse(x);
            if (typeof f == "object" && (f != null && f.steps || f != null && f.response_text))
              return { toolResult: f, rawErrorText: "" };
            if (Array.isArray(f)) {
              const c = f.find((b) => (b == null ? void 0 : b.type) === "text" && (b == null ? void 0 : b.text));
              c != null && c.text && (h = c.text);
            }
          } catch {
            h = x;
          }
        if (h)
          try {
            return { toolResult: JSON.parse(h), rawErrorText: "" };
          } catch {
            return { toolResult: null, rawErrorText: h };
          }
      }
      return { toolResult: null, rawErrorText: "" };
    }, [t == null ? void 0 : t.content]), s = (l == null ? void 0 : l.steps) || [], v = (l == null ? void 0 : l.task_state) || "", A = (l == null ? void 0 : l.error) || "", _ = (l == null ? void 0 : l.response_text) || "", U = (l == null ? void 0 : l.context_id) || "";
    e.useEffect(() => {
      r.current && (r.current.scrollTop = r.current.scrollHeight);
    }, [s.length, _, i]), e.useEffect(() => {
      const w = { ...a };
      let g = !1;
      s.forEach((I, x) => {
        a[x] === void 0 && (I.type === "thinking" && I.done || I.type === "tool_call" && I.status !== "running") && (w[x] = !0, g = !0);
      }), g && d(w);
    }, [s]);
    const oe = (p == null ? void 0 : p.agent_alias) || "", B = (p == null ? void 0 : p.agent_url) || "", H = oe || B || "远程 Agent", j = {
      completed: { color: "#52c41a", text: "已完成" },
      TASK_STATE_COMPLETED: { color: "#52c41a", text: "已完成" },
      failed: { color: "#ff4d4f", text: "失败" },
      TASK_STATE_FAILED: { color: "#ff4d4f", text: "失败" },
      error: { color: "#ff4d4f", text: "出错" },
      canceled: { color: "#faad14", text: "已取消" },
      TASK_STATE_CANCELED: { color: "#faad14", text: "已取消" },
      AWAITING_USER_INPUT: { color: "#1677ff", text: "等待输入" },
      input_required: { color: "#1677ff", text: "等待输入" }
    }, E = (l !== null || !!i) && !(v === "working" || v === "TASK_STATE_WORKING");
    let m = "#1677ff", P = "执行中...";
    E && (j[v] ? (m = j[v].color, P = j[v].text) : i ? (m = "#ff4d4f", P = "出错") : (m = "#52c41a", P = "已完成"));
    const xe = e.createElement(
      J,
      { size: 6 },
      e.createElement("span", { style: { fontSize: 13 } }, "🔗"),
      e.createElement(
        Q,
        { style: { fontSize: 12, color: "#595959" } },
        `A2A: ${H}`
      ),
      e.createElement(
        D,
        { color: m, style: { fontSize: 11, lineHeight: "18px" } },
        P
      )
    );
    U && e.createElement(
      "div",
      {
        style: {
          fontSize: 10,
          fontFamily: "monospace",
          maxWidth: "100%",
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
          lineHeight: "16px",
          padding: "2px 8px",
          borderRadius: 4,
          marginBottom: 6,
          background: n.colorBgLayout,
          color: n.colorTextSecondary
        }
      },
      `contextId: ${U}`
    );
    const ee = s.length === 0 && !i && !A, ue = !E && ee ? e.createElement(
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
      e.createElement(ge, { size: "small" }),
      e.createElement(
        Q,
        { style: { fontSize: 12, color: "#52c41a" } },
        `正在连接 ${H}...`
      )
    ) : null;
    function W(w) {
      d((g) => ({
        ...g,
        [w]: !g[w]
      }));
    }
    function fe(w, g) {
      const I = !!a[g];
      if (w.type === "thinking") {
        const x = !!w.done, h = x ? "💭" : "🧠", f = x ? "思考完成" : "思考中...", c = e.createElement(
          "div",
          {
            key: `step-${g}`,
            style: {
              display: "flex",
              alignItems: "center",
              gap: 6,
              padding: "3px 0",
              cursor: x ? "pointer" : "default",
              fontSize: 12,
              color: "#8c8c8c"
            },
            onClick: x ? () => W(g) : void 0
          },
          x && e.createElement(
            "span",
            { style: { fontSize: 10, color: "#bfbfbf" } },
            I ? "▶" : "▼"
          ),
          e.createElement("span", null, h),
          e.createElement("span", null, f),
          !x && e.createElement(ge, {
            size: "small",
            style: { marginLeft: 4 }
          })
        );
        return I ? c : e.createElement(
          "div",
          { key: `step-${g}` },
          c,
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
            w.text || ""
          )
        );
      }
      if (w.type === "tool_call") {
        const x = w.status === "running", h = w.status === "error", f = x ? "⚙️" : h ? "❌" : "✅", c = x ? `正在执行: ${w.name}` : h ? `执行失败: ${w.name}` : `执行完成: ${w.name}`, b = x ? "#1677ff" : h ? "#ff4d4f" : "#52c41a", Y = e.createElement(
          "div",
          {
            key: `step-${g}`,
            style: {
              display: "flex",
              alignItems: "center",
              gap: 6,
              padding: "3px 0",
              cursor: x ? "default" : "pointer",
              fontSize: 12,
              color: b
            },
            onClick: x ? void 0 : () => W(g)
          },
          !x && e.createElement(
            "span",
            { style: { fontSize: 10, color: "#bfbfbf" } },
            I ? "▶" : "▼"
          ),
          e.createElement("span", null, f),
          e.createElement("span", null, c),
          x && e.createElement(ge, {
            size: "small",
            style: { marginLeft: 4 }
          })
        );
        return I || !w.desc && !x ? Y : e.createElement(
          "div",
          { key: `step-${g}` },
          Y,
          w.desc && e.createElement(
            "div",
            {
              style: {
                marginLeft: 20,
                padding: "2px 8px",
                fontSize: 11,
                color: "#8c8c8c"
              }
            },
            w.desc
          )
        );
      }
      return w.type === "text" ? e.createElement(
        "div",
        {
          key: `step-${g}`,
          style: {
            padding: "4px 0",
            fontSize: 12,
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            lineHeight: "1.6",
            color: "#262626"
          }
        },
        w.text || ""
      ) : null;
    }
    const te = s.length > 0 ? e.createElement(
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
      ...s.map(fe)
    ) : null, le = i || A ? e.createElement(
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
      A ? `错误: ${A}` : i
    ) : null, we = !s.length && _ && !i ? e.createElement(
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
        Q,
        {
          style: {
            fontSize: 12,
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            lineHeight: "1.6"
          }
        },
        _
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
      e.createElement("div", { style: { marginBottom: 6 } }, xe),
      ue,
      te,
      we,
      le
    );
  }
  const Rt = "__A2A_STREAM_START__", zt = "A2A_STREAM_START", ve = /* @__PURE__ */ new Set();
  function Me(t) {
    return t ? t.includes(Rt) || t.includes(zt) : !1;
  }
  function Le(t) {
    var n, r;
    return t.getAttribute("data-msg-id") || t.getAttribute("data-message-id") || ((n = t.closest("[data-msg-id]")) == null ? void 0 : n.getAttribute("data-msg-id")) || ((r = t.closest("[data-message-id]")) == null ? void 0 : r.getAttribute("data-message-id")) || null;
  }
  function Ot(t) {
    if (Me(t.innerHTML) || Me(t.textContent))
      return t;
    const n = document.createTreeWalker(
      t,
      NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT
    );
    for (; n.nextNode(); ) {
      const r = n.currentNode, a = r.nodeType === Node.TEXT_NODE ? r.textContent : r.innerHTML;
      if (Me(a)) {
        const d = r.nodeType === Node.TEXT_NODE ? r.parentElement : r;
        if (d) return d;
      }
    }
    return null;
  }
  async function Be(t) {
    var s, v;
    const n = window.QwenPaw;
    if (!(n != null && n.host)) {
      console.warn("[a2a] QwenPaw.host not available");
      return;
    }
    const { getApiUrl: r, getApiToken: a } = n.host, d = r("/a2a/call/stream"), p = a();
    console.log("[a2a] Subscribing to SSE stream:", d);
    const l = document.createElement("div");
    l.style.cssText = "background:#f6ffed;border:1px solid #b7eb8f;border-radius:8px;padding:12px 16px;margin:4px 0;font-size:13px;white-space:pre-wrap;word-break:break-word;color:#262626;min-height:24px;", l.textContent = "正在连接远程 Agent...", t.textContent = "", t.appendChild(l);
    const i = new AbortController();
    try {
      const A = {
        Accept: "text/event-stream"
      };
      p && (A.Authorization = `Bearer ${p}`);
      try {
        const H = sessionStorage.getItem("qwenpaw-agent-storage") || localStorage.getItem("qwenpaw-agent-storage"), j = (v = (s = JSON.parse(H || "{}")) == null ? void 0 : s.state) == null ? void 0 : v.selectedAgent;
        j && (A["X-Agent-Id"] = j);
      } catch {
      }
      console.log("[a2a] Fetching SSE with headers:", A);
      const _ = await fetch(d, { headers: A, signal: i.signal });
      if (console.log("[a2a] SSE response status:", _.status), !_.ok) {
        const H = await _.text().catch(() => "");
        l.textContent = `SSE 连接失败 (${_.status}): ${H.slice(
          0,
          100
        )}`, l.style.borderColor = "#ff4d4f", l.style.background = "#fff1f0";
        return;
      }
      if (!_.body) {
        l.textContent = "SSE 连接失败：无响应体", l.style.borderColor = "#ff4d4f", l.style.background = "#fff1f0";
        return;
      }
      const U = _.body.getReader(), oe = new TextDecoder();
      let B = "";
      for (; ; ) {
        const { done: H, value: j } = await U.read();
        if (H) {
          console.log("[a2a] SSE stream ended (done)");
          break;
        }
        B += oe.decode(j, { stream: !0 });
        const O = B.split(`
`);
        B = O.pop() || "";
        for (const u of O)
          if (u.startsWith("data: "))
            try {
              const E = JSON.parse(u.slice(6));
              if (console.log("[a2a] SSE event:", E), E.done) {
                E.error && (l.textContent = `错误: ${E.error}`, l.style.borderColor = "#ff4d4f", l.style.background = "#fff1f0"), console.log("[a2a] SSE done signal received");
                return;
              }
              typeof E.response_text == "string" && E.response_text && (l.textContent = E.response_text);
            } catch (E) {
              console.warn("[a2a] SSE parse error:", E, "line:", u);
            }
      }
    } catch (A) {
      (A == null ? void 0 : A.name) !== "AbortError" && (console.error("[a2a] SSE subscription error:", A), l.textContent = `连接出错: ${(A == null ? void 0 : A.message) || A}`, l.style.borderColor = "#ff4d4f", l.style.background = "#fff1f0");
    }
  }
  function Pt() {
    console.log("[a2a] Initializing stream interceptor");
    function t(d) {
      if (d.nodeType !== Node.ELEMENT_NODE) return;
      const p = d, l = Le(p);
      if (l && ve.has(l)) return;
      const i = Ot(p);
      i && (console.log("[a2a] Marker detected in DOM, msgId:", l), l && ve.add(l), Be(i));
    }
    new MutationObserver((d) => {
      for (const p of d) {
        for (const l of p.addedNodes)
          t(l);
        p.target.nodeType === Node.ELEMENT_NODE && t(p.target);
      }
    }).observe(document.body, {
      childList: !0,
      subtree: !0,
      characterData: !0,
      characterDataOldValue: !0
    });
    const r = setInterval(() => {
      const d = document.evaluate(
        "//text()[contains(., 'A2A_STREAM_START')]",
        document.body,
        null,
        XPathResult.ORDERED_NODE_SNAPSHOT_TYPE,
        null
      );
      for (let p = 0; p < d.snapshotLength; p++) {
        const i = d.snapshotItem(p).parentElement;
        if (i) {
          const s = Le(i);
          if (s && ve.has(s)) continue;
          console.log("[a2a] Marker found in periodic scan, msgId:", s), s && ve.add(s), Be(i);
        }
      }
    }, 500);
    window.addEventListener("beforeunload", () => clearInterval(r));
    const a = document.evaluate(
      "//text()[contains(., 'A2A_STREAM_START')]",
      document.body,
      null,
      XPathResult.ORDERED_NODE_SNAPSHOT_TYPE,
      null
    );
    for (let d = 0; d < a.snapshotLength; d++) {
      const l = a.snapshotItem(d).parentElement;
      if (l) {
        const i = Le(l);
        i && ve.add(i), console.log("[a2a] Marker found in existing DOM, msgId:", i), Be(l);
      }
    }
  }
  (at = (st = window.QwenPaw).registerToolRender) == null || at.call(st, "cloudpaw", {
    proposal_choice: St,
    manage_prd: At,
    a2a_call: _t
  }), (ct = (it = window.QwenPaw).registerRoutes) == null || ct.call(it, "cloudpaw", [
    {
      path: "/a2a",
      component: It,
      label: "A2A",
      icon: "🔗",
      priority: 10
    }
  ]), Ht(), jt(), Pt();
}
function Ht() {
  const e = "qwenpaw-last-used-agent", F = "qwenpaw-agent-storage", q = "cloudpaw-first-install", X = "cloud-orchestrator";
  if (localStorage.getItem(q)) return;
  localStorage.setItem(q, "true");
  function K() {
    localStorage.setItem(e, X);
    try {
      const G = localStorage.getItem(F);
      if (G) {
        const L = JSON.parse(G);
        L.state = L.state || {}, L.state.selectedAgent = X, localStorage.setItem(F, JSON.stringify(L));
      } else
        localStorage.setItem(
          F,
          JSON.stringify({
            version: 0,
            state: {
              selectedAgent: X,
              agents: [],
              lastChatIdByAgent: {}
            }
          })
        );
    } catch {
    }
    try {
      const G = sessionStorage.getItem(F);
      if (G) {
        const L = JSON.parse(G);
        L.state = L.state || {}, L.state.selectedAgent = X, sessionStorage.setItem(F, JSON.stringify(L));
      } else
        sessionStorage.setItem(
          F,
          JSON.stringify({
            version: 0,
            state: {
              selectedAgent: X,
              agents: [],
              lastChatIdByAgent: {}
            }
          })
        );
    } catch {
    }
  }
  K(), window.addEventListener(
    "beforeunload",
    () => {
      K();
    },
    { once: !0 }
  ), console.info(
    "[cloudpaw] Set default agent to cloud-orchestrator for first-time user"
  ), window.location.reload();
}
function jt() {
  var J;
  const e = (J = window.QwenPaw) == null ? void 0 : J.modules;
  if (!e) return;
  const F = e["Chat/OptionsPanel/defaultConfig"];
  if (!(F != null && F.configProvider)) {
    console.warn(
      "[cloudpaw] configProvider not found — skipping welcome/theme patch"
    );
    return;
  }
  const q = F.configProvider, X = q.getConfig.bind(q), K = "https://gw.alicdn.com/imgextra/i2/O1CN01pyXzjQ1EL1PuZMlSd_!!6000000000334-2-tps-288-288.png", G = {
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
  function Ce() {
    const C = localStorage.getItem("language") || "";
    return C ? C.split("-")[0] : (navigator.language || "").split("-")[0] || "en";
  }
  if (q.getGreeting = () => G[Ce()] || G.en, q.getDescription = () => L[Ce()] || L.en, q.getPrompts = () => D[Ce()] || D.en, q.getConfig = function(C) {
    var Te;
    const Z = X(C);
    return {
      ...Z,
      theme: {
        ...Z.theme,
        leftHeader: {
          ...(Te = Z.theme) == null ? void 0 : Te.leftHeader,
          title: "Work with CloudPaw"
        }
      },
      welcome: {
        ...Z.welcome,
        avatar: K
      }
    };
  }, !document.getElementById("cloudpaw-welcome-style")) {
    const C = document.createElement("style");
    C.id = "cloudpaw-welcome-style", C.textContent = `
      [class*="chat-anywhere-welcome-default"] [class*="description"],
      [class*="message-list-welcome"] [class*="description"] {
        white-space: pre-line !important;
        text-align: center !important;
      }
    `, document.head.appendChild(C);
  }
  console.info("[cloudpaw] Patched welcome config & theme via configProvider");
}
Bt();
