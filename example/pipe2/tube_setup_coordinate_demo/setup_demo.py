# 单次事务保证整套演示配置同时生效，任一字段无效时不留下半成品。
with 管状.事务():
    管状.创建操作(name="Tube Thin-Wall Indexed · Pipe2 Demo")
    管状.确认零件(
        part_body_ids=("body_001", "body_002"),
        ignored_body_ids=(),
    )
    管状.设置机床("builtin.machine.generic_xyzac_reference.v1")

    # 以下喷嘴尺寸只用于走通 Setup 门禁，真实项目应替换为图纸或实测数据。
    管状.设置喷嘴(
        "2217947b-af31-52a4-9f54-3e920734d78e",
        interface="M6×1",
        length_mm=12.5,
        use_collision_envelope=True,
    )
    管状.设置材料(
        "0ff92885-617b-4144-a03c-9989872454bc",
        review_confirmed=True,
    )
    管状.设置模型坐标(
        origin=(0, 0, 0),
        z=(0, 0, 1),
        x=(1, 0, 0),
        input_frame="source",
    )
    管状.设置构建坐标(
        origin=(0, 0, 0),
        z=(0, 0, 1),
        x=(1, 0, 0),
        input_frame="model",
    )
    管状.设置装夹(
        "build_plate_mount",
        translation_mm=(0, 0, 0),
        rotation_xyz_deg=(0, 0, 0),
    )
