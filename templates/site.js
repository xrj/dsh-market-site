/* 首页目录交互：只处理公开 data.json，不在浏览器里请求任何第三方服务。 */
(function () {
  "use strict";

  var PAGE_SIZE = 24;
  var state = {
    data: null,
    query: "",
    category: "all",
    type: "all",
    sort: "stars",
    page: 1
  };

  var refs = {
    categoryNav: document.getElementById("category-nav"),
    featuredSection: document.getElementById("featured-section"),
    featuredGrid: document.getElementById("featured-grid"),
    featuredSummary: document.getElementById("featured-summary"),
    projectGrid: document.getElementById("project-grid"),
    resultCount: document.getElementById("result-count"),
    query: document.getElementById("query"),
    typeFilter: document.getElementById("type-filter"),
    sortFilter: document.getElementById("sort-filter"),
    loadMore: document.getElementById("load-more")
  };

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function numberText(value) {
    return new Intl.NumberFormat("zh-CN").format(Number(value) || 0);
  }

  function categoryMap() {
    var map = {};
    (state.data.categories || []).forEach(function (category) {
      map[category.id] = category;
    });
    return map;
  }

  function typeMap() {
    var map = {};
    (state.data.types || []).forEach(function (type) {
      map[type.id] = type;
    });
    return map;
  }

  function ownerInfo(item) {
    if (item.owner && typeof item.owner === "object") {
      return {
        login: item.owner.login || String(item.fullName || "").split("/")[0] || "未知作者",
        avatarUrl: item.owner.avatarUrl || ""
      };
    }
    return {
      login: typeof item.owner === "string" ? item.owner : String(item.fullName || "").split("/")[0] || "未知作者",
      avatarUrl: ""
    };
  }

  function avatarUrl(item) {
    var owner = ownerInfo(item);
    if (owner.avatarUrl) {
      return owner.avatarUrl;
    }
    return "https://github.com/" + encodeURIComponent(owner.login) + ".png?size=80";
  }

  function updatedLabel(value) {
    var timestamp = Date.parse(value || "");
    if (Number.isNaN(timestamp)) {
      return "未标注更新";
    }
    var days = Math.max(0, Math.round((Date.now() - timestamp) / 86400000));
    if (days === 0) {
      return "今天更新";
    }
    if (days === 1) {
      return "昨天更新";
    }
    if (days < 8) {
      return days + " 天前更新";
    }
    return "更新 " + new Date(timestamp).toISOString().slice(0, 10);
  }

  function detailUrl(item) {
    return "plugins/" + encodeURIComponent(item.detailSlug || item.slug) + "/";
  }

  function cardHtml(item, index, featured) {
    var categories = categoryMap();
    var types = typeMap();
    var category = categories[item.category] || { label: "开发与自动化" };
    var type = types[item.projectType] || { label: "插件" };
    var owner = ownerInfo(item);
    var context = (featured ? "推荐 · " : "") + category.label + " · " + type.label;
    var rank = featured ? String(index + 1).padStart(2, "0") : "";
    var description = item.description || "这个项目暂未提供说明。";
    return [
      '<a class="plugin-card',
      featured ? " is-featured" : "",
      '" href="',
      escapeHtml(detailUrl(item)),
      '" aria-label="查看 ',
      escapeHtml(item.name),
      ' 的详情">',
      '<img class="card-avatar" loading="lazy" src="',
      escapeHtml(avatarUrl(item)),
      '" alt="">',
      '<span class="card-identity">',
      '<span class="card-context">',
      escapeHtml(context),
      "</span>",
      '<strong class="card-title">',
      escapeHtml(item.name),
      "</strong>",
      '<span class="card-owner">',
      escapeHtml(owner.login),
      "</span>",
      "</span>",
      '<span class="card-rank" aria-hidden="true">',
      rank,
      "</span>",
      '<span class="card-description">',
      escapeHtml(description),
      "</span>",
      '<span class="card-meta">',
      "<span>Star ",
      numberText(item.stars),
      "</span>",
      "<span>",
      escapeHtml(item.language || "未标注语言"),
      "</span>",
      "<span>",
      escapeHtml(updatedLabel(item.pushedAt)),
      "</span>",
      "</span>",
      "</a>"
    ].join("");
  }

  function sortedFilteredItems() {
    var query = state.query.trim().toLowerCase();
    var items = (state.data.items || []).filter(function (item) {
      if (state.category !== "all" && item.category !== state.category) {
        return false;
      }
      if (state.type !== "all" && item.projectType !== state.type) {
        return false;
      }
      if (!query) {
        return true;
      }
      var owner = ownerInfo(item);
      var haystack = [
        item.name,
        item.fullName,
        owner.login,
        item.description,
        (item.topics || []).join(" ")
      ].join(" ").toLowerCase();
      return haystack.indexOf(query) !== -1;
    });
    items.sort(function (left, right) {
      if (state.sort === "updated") {
        return Date.parse(right.pushedAt || 0) - Date.parse(left.pushedAt || 0);
      }
      if (state.sort === "created") {
        return Date.parse(right.createdAt || 0) - Date.parse(left.createdAt || 0);
      }
      if (state.sort === "name") {
        return String(left.name || "").localeCompare(String(right.name || ""), "zh-CN");
      }
      return (Number(right.stars) || 0) - (Number(left.stars) || 0);
    });
    return items;
  }

  function featuredItems() {
    var byFullName = {};
    (state.data.items || []).forEach(function (item) {
      byFullName[item.fullName] = item;
    });
    var curated = (state.data.curatedOrder || []).map(function (fullName) {
      return byFullName[fullName];
    }).filter(Boolean);
    if (!curated.length) {
      curated = (state.data.items || []).filter(function (item) {
        return item.featured && !item.archived;
      });
    }
    if (!curated.length) {
      curated = (state.data.items || []).slice().sort(function (left, right) {
        return (Number(right.stars) || 0) - (Number(left.stars) || 0);
      });
    }
    return curated.slice(0, 6);
  }

  function renderCategories() {
    var counts = {};
    (state.data.items || []).forEach(function (item) {
      counts[item.category] = (counts[item.category] || 0) + 1;
    });
    var html = [
      '<button class="category-button',
      state.category === "all" ? " is-active" : "",
      '" type="button" data-category="all" aria-pressed="',
      state.category === "all" ? "true" : "false",
      '"><span>全部项目</span><small>',
      numberText((state.data.items || []).length),
      "</small></button>"
    ];
    (state.data.categories || []).forEach(function (category) {
      var active = state.category === category.id;
      html.push(
        '<button class="category-button',
        active ? " is-active" : "",
        '" type="button" data-category="',
        escapeHtml(category.id),
        '" aria-pressed="',
        active ? "true" : "false",
        '" style="--category-color:',
        escapeHtml(category.color || "#3d72a3"),
        '"><span>',
        escapeHtml(category.label),
        "</span><small>",
        numberText(counts[category.id] || 0),
        "</small></button>"
      );
    });
    refs.categoryNav.innerHTML = html.join("");
  }

  function renderTypes() {
    var counts = {};
    (state.data.items || []).forEach(function (item) {
      counts[item.projectType] = (counts[item.projectType] || 0) + 1;
    });
    var html = ['<option value="all">全部类型</option>'];
    (state.data.types || []).forEach(function (type) {
      if (!counts[type.id]) {
        return;
      }
      html.push(
        '<option value="',
        escapeHtml(type.id),
        '">',
        escapeHtml(type.label),
        "</option>"
      );
    });
    refs.typeFilter.innerHTML = html.join("");
    refs.typeFilter.value = state.type;
  }

  function renderFeatured() {
    var items = featuredItems();
    refs.featuredGrid.innerHTML = items.length
      ? items.map(function (item, index) { return cardHtml(item, index, true); }).join("")
      : '<p class="empty-copy">暂时没有推荐项目。</p>';
    refs.featuredSummary.textContent = items.length ? "推荐 " + items.length + " 个项目" : "";
  }

  function renderGrid() {
    var items = sortedFilteredItems();
    var visible = items.slice(0, state.page * PAGE_SIZE);
    refs.projectGrid.innerHTML = visible.length
      ? visible.map(function (item, index) { return cardHtml(item, index, false); }).join("")
      : '<p class="empty-copy">没有找到匹配的项目。试试换一个关键词或分类。</p>';
    refs.resultCount.textContent = "显示 " + visible.length + " / " + items.length + " 个项目";
    refs.loadMore.hidden = visible.length >= items.length;
  }

  function render() {
    var hasFilter = state.category !== "all" || state.type !== "all" || state.query.trim() !== "";
    refs.featuredSection.hidden = hasFilter;
    renderCategories();
    renderGrid();
    if (!hasFilter) {
      renderFeatured();
    }
  }

  function resetAndRender() {
    state.page = 1;
    render();
  }

  function bindEvents() {
    var inputTimer = 0;
    refs.categoryNav.addEventListener("click", function (event) {
      var button = event.target.closest("[data-category]");
      if (!button) {
        return;
      }
      state.category = button.getAttribute("data-category") || "all";
      resetAndRender();
    });
    refs.query.addEventListener("input", function () {
      window.clearTimeout(inputTimer);
      inputTimer = window.setTimeout(function () {
        state.query = refs.query.value;
        resetAndRender();
      }, 150);
    });
    refs.typeFilter.addEventListener("change", function () {
      state.type = refs.typeFilter.value;
      resetAndRender();
    });
    refs.sortFilter.addEventListener("change", function () {
      state.sort = refs.sortFilter.value;
      resetAndRender();
    });
    refs.loadMore.addEventListener("click", function () {
      state.page += 1;
      renderGrid();
    });
  }

  function showDataError() {
    refs.projectGrid.innerHTML = '<p class="empty-copy">项目数据暂时无法读取，请稍后再试。</p>';
    refs.featuredSection.hidden = true;
    refs.loadMore.hidden = true;
  }

  function boot(data) {
    if (!data || !Array.isArray(data.items)) {
      showDataError();
      return;
    }
    state.data = data;
    renderTypes();
    renderFeatured();
    render();
    bindEvents();
  }

  fetch("data.json", { cache: "no-store" })
    .then(function (response) {
      if (!response.ok) {
        throw new Error("data.json 请求失败");
      }
      return response.json();
    })
    .then(boot)
    .catch(showDataError);
}());
