"""Read local V2Ray GeoSite domain entries for text configuration exports."""
from pathlib import Path


def protobuf_fields(raw):
    offset = 0

    def number():
        nonlocal offset
        value = 0
        for shift in range(0, 70, 7):
            if offset >= len(raw):
                break
            byte = raw[offset]
            offset += 1
            value |= (byte & 127) << shift
            if byte < 128:
                return value
        raise ValueError("GeoSite 数据库格式错误")

    while offset < len(raw):
        tag = number()
        wire = tag & 7
        if wire == 0:
            value = number()
        elif wire in (1, 2, 5):
            size = number() if wire == 2 else {1: 8, 5: 4}[wire]
            if offset + size > len(raw):
                raise ValueError("GeoSite 数据库不完整")
            value = raw[offset:offset + size]
            offset += size
        else:
            raise ValueError("GeoSite 数据库包含不支持的数据类型")
        yield tag >> 3, value


def geosite_domains(path, categories):
    requested = set(categories)
    if not requested:
        return {}
    try:
        raw = Path(path).read_bytes()
    except OSError:
        raise ValueError("无法读取青云梯 GeoSite.dat，请保留安装目录中的规则数据库后再下载 DNS 与分流配置") from None
    result = {}
    try:
        for field, entry in protobuf_fields(raw):
            if field != 1:
                continue
            fields = list(protobuf_fields(entry))
            code = next(value.decode('utf-8').lower() for key, value in fields if key == 1)
            matches = [category for category in requested if category.lower().split('@')[0] == code]
            if not matches:
                continue
            domains = []
            for key, value in fields:
                if key != 2:
                    continue
                domain = list(protobuf_fields(value))
                values = dict((key, value) for key, value in domain if key != 3)
                attributes = [dict(protobuf_fields(value)) for key, value in domain if key == 3]
                attributes = {item[1].decode('utf-8').lower() for item in attributes if item.get(2) == 1}
                kind, text = values.get(1, 0), values[2].decode('utf-8')
                if kind not in (0, 1, 2, 3) or '\n' in text or '\r' in text:
                    raise ValueError("GeoSite 数据库包含不支持的域名条目")
                domains.append((kind, text, attributes))
            for category in matches:
                attributes = category.lower().split('@')[1:]
                result[category] = [(kind, text) for kind, text, present in domains
                    if all((attr[1:] not in present) if attr.startswith('!') else (attr in present)
                           for attr in attributes)]
    except (KeyError, TypeError, AttributeError, UnicodeError, StopIteration):
        raise ValueError("GeoSite 数据库格式错误") from None
    if any(not result.get(category) for category in requested):
        raise ValueError("GeoSite 数据库缺少所需分类，请更新青云梯规则数据库后重新导出")
    return result
