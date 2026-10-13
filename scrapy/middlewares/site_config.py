"""站点级反爬配置查找（UA / 代理中间件与爬虫共用；经 middlewares 包重导出）"""


def _get_site_config(spider) -> dict:
    """根据 spider.name 查找站点配置（sites.yml 中的站点段）

    配置路径：Scrapy settings.SITE_CONFIG → {sites: {<name>: {anti_crawl: {...}}}}
    或扁平化后直接 {<name>: {anti_crawl: {...}}}（取决于 Dynaconf 加载方式）。
    返回空 dict 表示无站点级覆盖，回退全局设置。
    """
    if spider is None:
        return {}
    settings_obj = getattr(spider, "settings", None)
    if settings_obj is None:
        return {}
    sites_cfg = settings_obj.get("SITE_CONFIG", {}) or {}
    # Dynaconf 把 sites.yml 的顶层键 "sites" 作为命名空间
    inner = sites_cfg.get("sites", sites_cfg) if isinstance(sites_cfg, dict) else {}
    site = inner.get(spider.name, {}) if isinstance(inner, dict) else {}
    return site if isinstance(site, dict) else {}
