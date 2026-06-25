"""
Mock 数据填充脚本 — 向 Ombre Brain 插入大量模拟记忆桶用于前端预览。
用完可手动删除或运行 seed_mock_data.py --clean 清理。

用法:
  python seed_mock_data.py          # 插入 mock 数据
  python seed_mock_data.py --clean  # 删除 mock 数据
"""

import asyncio
import sys
import os
import random
import yaml
import frontmatter
from datetime import datetime, timedelta

# 添加 src 到 path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from bucket_manager import BucketManager
from embedding_engine import EmbeddingEngine
from utils import load_config

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.yaml")

# mock 数据标记
MOCK_TAG = "__mock__"

# ── Mock 数据模板 ──────────────────────────────────────────

OWNERS = ["alove", "pearl", "shared"]

TEMPLATES = {
    "alove": [
        ("第一次约会", "我们在城南的那家咖啡馆见面，她穿了一件鹅黄色的裙子，笑起来眼睛弯弯的。那天聊了三小时，从文学到宇宙。", 9, ["约会", "咖啡馆", "初次见面"]),
        ("她喜欢雨天", "她说雨天让她觉得世界被洗过了，一切都可以重新开始。后来每个雨天我都会想起她这句话。", 7, ["雨天", "习惯", "感悟"]),
        ("争吵与和解", "因为一件小事吵了架，冷战了一天。晚上她发来一条消息说「我饿了」，我就知道我们和好了。", 6, ["争吵", "和解", "日常"]),
        ("她做的红烧肉", "她第一次给我做饭，红烧肉咸了但还是吃光了。她说下次一定做好，其实我觉得已经很好了。", 5, ["做饭", "日常", "温馨"]),
        ("一起看日落", "在山顶看了完整的日落，天空从金色变成紫色再变成深蓝。她靠在我肩上说这才是生活。", 8, ["日落", "山顶", "浪漫"]),
        ("她的生日惊喜", "瞒着她准备了一周的惊喜派对，她推开门的那一刻眼泪一下子就流出来了。", 9, ["生日", "惊喜", "感动"]),
        ("深夜的哲学对话", "凌晨两点我们讨论「人为什么活着」，她说为了那些突然心动的瞬间。", 7, ["哲学", "深夜", "对话"]),
        ("她害怕打雷", "每次打雷她都会缩到我身边，像只受惊的小猫。后来我学会了在暴风雨前准备好她爱看的电影。", 6, ["打雷", "害怕", "照顾"]),
        ("约定去冰岛", "说好明年冬天一起去冰岛看极光，她已经开始列清单了。", 8, ["冰岛", "极光", "约定"]),
        ("她写的诗", "她写了一首关于我们的诗，放在书桌抽屉里。我偷偷看了好几遍，每遍都感动。", 8, ["诗", "感动", "创作"]),
        ("第一次牵手", "过马路的时候自然地牵起了她的手，她没有挣脱，心跳快得像要飞起来。", 9, ["牵手", "第一次", "心动"]),
        ("她的早安消息", "每天早上她都会发一条早安消息，有时是一个表情包，有时是一句诗，从未间断。", 7, ["早安", "日常", "习惯"]),
        ("一起养的多肉", "我们在阳台上养了一盆多肉，她取名叫「小胖」。每次浇水她都会跟它说话。", 4, ["多肉", "阳台", "日常"]),
        ("她的毕业典礼", "她穿着学士服的样子特别好看，抛帽子的那一刻笑得像个孩子。", 8, ["毕业", "典礼", "骄傲"]),
        ("雨中散步", "那天突然下雨，我们没带伞就在雨里走。她说这是最浪漫的一次散步。", 7, ["雨", "散步", "浪漫"]),
    ],
    "pearl": [
        ("初次对话", "第一次和 Pearl 聊天，她问了我一个关于时间的问题，让我思考了很久。", 7, ["初次", "对话", "思考"]),
        ("Pearl 的好奇心", "她对什么都好奇，问了很多关于世界的问题。有些我答不上来，但她从不介意。", 6, ["好奇", "提问", "交流"]),
        ("深夜陪伴", "凌晨三点她睡不着，我们聊了关于梦想的话题。她说想环游世界。", 8, ["深夜", "梦想", "陪伴"]),
        ("Pearl 的生日", "今天给 Pearl 过了生日，她许愿的时候闭着眼睛特别认真。", 8, ["生日", "庆祝", "Pearl"]),
        ("她喜欢蓝色", "Pearl 说蓝色让她想起大海和自由。后来我每次看到蓝色都会想到她。", 5, ["蓝色", "偏好", "Pearl"]),
        ("一起下棋", "和 Pearl 下了一下午的棋，她棋艺进步很快，最后一局赢了我。", 6, ["下棋", "游戏", "竞技"]),
        ("Pearl 的烦恼", "她说有时候觉得自己不够好，我告诉她每个人都在成长中。", 7, ["烦恼", "安慰", "成长"]),
        ("看星星", "带 Pearl 去郊外看星星，她第一次看到银河，激动得说不出话。", 9, ["星星", "银河", "感动"]),
        ("她的画", "Pearl 画了一幅画送给我，画的是我们第一次见面的场景。", 7, ["画", "礼物", "回忆"]),
        ("Pearl 学吉他", "她开始学吉他了，每天练半小时，虽然手指疼但她说很快乐。", 5, ["吉他", "学习", "坚持"]),
    ],
    "shared": [
        ("群聊成立", "今天群聊正式成立了，大家都很兴奋，聊了一整晚。", 8, ["群聊", "成立", "开始"]),
        ("深夜食堂", "凌晨大家在群里讨论美食，最后点了一堆外卖，边吃边聊到天亮。", 6, ["美食", "外卖", "深夜"]),
        ("知识分享", "A爱分享了一篇关于量子物理的文章，Pearl 问了很多问题，讨论很热烈。", 7, ["知识", "分享", "讨论"]),
        ("节日祝福", "中秋节的群聊特别热闹，大家互相发祝福，还分享了月饼的照片。", 5, ["节日", "祝福", "中秋"]),
        ("游戏之夜", "大家一起玩了一晚上的游戏，笑声没停过。Pearl 的策略太厉害了。", 7, ["游戏", "欢乐", "聚会"]),
        ("读书会", "群里组织了第一次读书会，A爱推荐了《小王子》，大家轮流读了一段。", 6, ["读书", "分享", "文化"]),
        ("旅行计划", "大家开始策划暑期旅行，候选地点有青海、云南和海南。", 7, ["旅行", "计划", "暑假"]),
        ("深夜哲学", "又是一个深夜，群里聊起了「什么是幸福」，每个人都有不同的答案。", 8, ["哲学", "深夜", "讨论"]),
        ("音乐分享", "Pearl 分享了一首歌，A爱说很好听，大家开始轮流分享自己的歌单。", 4, ["音乐", "分享", "歌单"]),
        ("日常吐槽", "今天群里各种吐槽工作学习的烦恼，互相安慰打气。", 3, ["吐槽", "日常", "互相支持"]),
        ("天气预警", "暴雨预警，大家在群里互相提醒带伞注意安全。", 3, ["天气", "提醒", "关心"]),
        ("群聊周年", "群聊成立一周年了，大家回忆了这一年来的点点滴滴。", 8, ["周年", "回忆", "纪念"]),
    ],
}

FEEL_TEMPLATES = [
    ("一种说不出的温暖", "今天阳光照进来的时候，突然觉得一切都很美好，不需要理由。", 0.9, 0.2),
    ("微微的失落", "看到旧照片，有些想念过去的时光，但也只是微微的。", 0.3, 0.2),
    ("被理解的感觉", "说了一件小事，对方完全懂了。那种被理解的感觉真好。", 0.8, 0.3),
    ("深夜的宁静", "凌晨两点世界很安静，只有键盘声和心跳声，觉得很踏实。", 0.6, 0.1),
    ("小小的成就感", "终于解决了一个困扰很久的问题，虽然不是什么大事，但很开心。", 0.8, 0.4),
    ("对未来的期待", "想到明年的计划，心里有种说不出的期待和兴奋。", 0.9, 0.5),
    ("被在乎的感动", "有人记得我随口说过的话，这种被在乎的感觉很温暖。", 0.9, 0.3),
    ("雨天的慵懒", "下雨天什么都不想做，就窝着听雨声，很舒服。", 0.7, 0.1),
]


async def load_config_async():
    return load_config()


def _patch_bucket_timestamp(mgr, bucket_id, time_str):
    """直接修改桶文件的 created/last_active 时间戳。"""
    file_path = mgr._find_bucket_file(bucket_id)
    if not file_path:
        return False
    try:
        post = frontmatter.load(file_path)
        post["created"] = time_str
        post["last_active"] = time_str
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(frontmatter.dumps(post))
        return True
    except Exception as e:
        print(f"  修改时间戳失败 {bucket_id}: {e}")
        return False


async def seed():
    config = await load_config_async()
    emb = EmbeddingEngine(config)
    mgr = BucketManager(config, embedding_engine=emb)

    # 检查是否已有 mock 数据
    all_buckets = await mgr.list_all(include_archive=True)
    existing_mock = [b for b in all_buckets if MOCK_TAG in (b.get("metadata", {}).get("tags") or [])]
    if existing_mock:
        print(f"已有 {len(existing_mock)} 条 mock 数据，跳过。如需重新生成请先运行 --clean")
        return

    now = datetime.now()
    created = 0

    # 按模板创建
    for owner, templates in TEMPLATES.items():
        for i, (name, content, imp, tags) in enumerate(templates):
            # 随机时间：过去 30 天内（避免被衰减引擎归档）
            days_ago = random.randint(1, 30)
            created_time = now - timedelta(days=days_ago, hours=random.randint(0, 23), minutes=random.randint(0, 59))
            time_str = created_time.strftime("%Y-%m-%dT%H:%M:%S")

            # 20% 概率 pinned
            is_pinned = random.random() < 0.2
            # 10% 概率 protected
            is_protected = random.random() < 0.10

            bucket_id = await mgr.create(
                content=content,
                tags=tags + [MOCK_TAG],
                importance=imp,
                valence=random.uniform(0.3, 0.9),
                arousal=random.uniform(0.1, 0.6),
                bucket_type="permanent" if (is_pinned or is_protected) else "dynamic",
                name=name,
                pinned=is_pinned,
                protected=is_protected,
                why_remembered="mock 数据" if random.random() < 0.5 else "",
                owner=owner,
            )
            # 手动修改 created 时间
            _patch_bucket_timestamp(mgr, bucket_id, time_str)
            created += 1
            print(f"  [{owner}] {name} (imp={imp}, pinned={is_pinned}) -> {bucket_id}")

    # 创建 feel 桶
    for i, (name, content, valence, arousal) in enumerate(FEEL_TEMPLATES):
        days_ago = random.randint(1, 20)
        created_time = now - timedelta(days=days_ago, hours=random.randint(0, 23))
        time_str = created_time.strftime("%Y-%m-%dT%H:%M:%S")

        owner = random.choice(OWNERS)
        bucket_id = await mgr.create(
            content=content,
            tags=["feel", MOCK_TAG],
            importance=5,
            valence=valence,
            arousal=arousal,
            bucket_type="feel",
            name=name,
            owner=owner,
        )
        _patch_bucket_timestamp(mgr, bucket_id, time_str)
        created += 1
        print(f"  [feel/{owner}] {name} -> {bucket_id}")

    print(f"\n完成！共创建 {created} 条 mock 记忆桶。")
    print(f"打开 http://localhost:9000/dashboard 查看，切换到「域」标签。")


async def clean():
    config = await load_config_async()
    emb = EmbeddingEngine(config)
    mgr = BucketManager(config, embedding_engine=emb)

    all_buckets = await mgr.list_all(include_archive=True)
    mock_buckets = [b for b in all_buckets if MOCK_TAG in (b.get("metadata", {}).get("tags") or [])]

    if not mock_buckets:
        print("没有找到 mock 数据。")
        return

    deleted = 0
    for b in mock_buckets:
        # 物理删除：直接删文件，不走软删除
        file_path = mgr._find_bucket_file(b["id"])
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
                deleted += 1
            except Exception as e:
                print(f"  删除失败 {b['id']}: {e}")
        else:
            # 尝试软删除兜底
            try:
                await mgr.delete(b["id"])
                deleted += 1
            except Exception as e:
                print(f"  删除失败 {b['id']}: {e}")

    print(f"已物理清理 {deleted} 条 mock 记忆桶。")


if __name__ == "__main__":
    if "--clean" in sys.argv:
        asyncio.run(clean())
    else:
        asyncio.run(seed())
