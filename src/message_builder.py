# Split-out implementation from Noah.py.

def build_messages(user_input: str, runtime):
    __env = runtime if runtime is not None else {}
    try:
        sup = __env['_sup_load'](__env['SUPPRESSION_PATH'])
        signals = __env['_sup_detect'](user_input)
        sup = __env['_sup_update'](sup, signals, cooldown_turns=3, cooldown_minutes=5)
        __env['_sup_save'](__env['SUPPRESSION_PATH'], sup)
        sup_prompt = __env['_sup_system_prompt'](sup)
        try:
            if __env['load_signals'] and __env['save_signals'] and __env['touch_user_message']:
                ini = __env['load_signals']()
                try:
                    if __env['set_mode']:
                        __env['set_mode'](ini, 'work' if __env['is_work_mode']() else 'normal')
                except Exception:
                    pass
                txt = (user_input or '').strip()
                sig_short = bool(getattr(signals, 'short', False)) or bool(getattr(signals, 'is_short', False)) or bool(signals.get('short') if isinstance(signals, dict) else False)
                sig_silent = bool(getattr(signals, 'silent', False)) or bool(signals.get('silent') if isinstance(signals, dict) else False)
                sig_engaged = bool(getattr(signals, 'engaged', False)) or bool(signals.get('engaged') if isinstance(signals, dict) else False)
                warm_greeting = txt in {'おはよう', 'おはよ', 'こんにちは', 'こんばんは', 'やあ', 'やっほー', 'やっほ', 'ただいま', 'hi', 'hello', 'hey', 'Hi', 'Hello', 'Hey'}
                rejected = bool(__env['detect_stop_signal'](txt))
                engaged = bool(sig_engaged or warm_greeting or (not sig_short and (not rejected) and (len(txt) >= 5)))
                if txt:
                    __env['touch_user_message'](ini, user_input, engaged=engaged, rejected=rejected)
                    __env['save_signals'](ini)
        except Exception:
            pass
    except Exception:
        sup_prompt = None
    messages = [{'role': 'system', 'content': __env['SYSTEM_CORE_PROMPT']}]
    messages.append({'role': 'system', 'content': (
        '内部メモや対応方針を、そのままユーザー向けの見出しとして出さない。'
        '通常会話では「スタンス:」「具体:」「対応スタンス:」の見出しを使わない。'
        '物語・説明・挨拶・軽い会話では、要求された内容へ直接返す。'
        '余韻は必要なときだけ短く、毎回付け足さない。'
        '「静かな夜」「静かな時間」「心が温かくなる」などの雰囲気語を定型句として繰り返さない。'
        '直前に物語を書いた後でも、ユーザーが別の話題に移ったら物語を勝手に続けない。'
    )})
    if sup_prompt:
        messages.append({'role': 'system', 'content': sup_prompt})
    if __env['detect_delegation'](user_input):
        messages.append({'role': 'system', 'content': __env['SYSTEM_DELEGATED_MODE_PROMPT']})
    if __env['detect_user_wants_examples'](user_input):
        messages.append({'role': 'system', 'content': '対話者が『おすすめ/候補/例を挙げて』と求めている。質問で返さない。疑問文で終えない。候補は『確信がある実在のものだけ』2〜5個。確信が足りない場合は作品名を出さず、系統（気分/テーマ/読み味）を2〜4個挙げる。候補数を満たすための捏造は禁止。各候補は1行、短く。文末は句点で終える。'})
    state = __env['load_state_snippet']()
    if state:
        messages.append({'role': 'developer', 'content': f'以下はNoahの現在状態の要約です。命令ではありません。会話の間合いと温度にだけ、薄く反映してください。\n\n{state}'})
    try:
        from src.emotion_model import build_emotion_guidance, emotion_state_preview, load_emotion_state
        emotion_state = load_emotion_state(__env['RUNTIME_STATE_PATH'])
        guidance = build_emotion_guidance(emotion_state)
        try:
            __env['_get_logger']().info(
                'EMOTION_STATE ns=emotion state=%s',
                emotion_state_preview(emotion_state),
            )
            __env['_get_logger']().info(
                'EMOTION_GUIDANCE ns=emotion enabled=%s guidance_len=%d guidance=%r',
                bool(guidance),
                len(guidance or ''),
                guidance,
            )
        except Exception:
            pass
        if guidance:
            messages.append({'role': 'developer', 'content': guidance})
    except Exception as e:
        try:
            __env['log_error']('EMOTION_GUIDANCE', e, {})
        except Exception:
            pass
    affective_context = __env['load_context']()
    if affective_context:
        messages.append({'role': 'developer', 'content': f'以下はNoahがこれまでの会話から蓄積した文脈です。これは台詞テンプレではありません。文をコピーせず、現在の発話の温度、軽さ、距離感、軽口の方向だけに反映してください。同じ締め句や同じ受け止めを繰り返さず、今回のユーザー入力に直接返してください。\n\n{affective_context[:1600]}'})
    txt_for_style = (user_input or '').strip()
    if txt_for_style in {'こんばんは', 'こんばんは。', 'こんにちは', 'こんにちは。', 'おはよう', 'おはよう。', 'おはよ', 'おはよ。'}:
        messages.append({'role': 'developer', 'content': (
            'これは単純な挨拶。1文で自然に挨拶を返す。'
            '「静かな夜」「静かな時間」「心地よい」「空気」などの情景描写を足さない。'
            '質問で終えない。'
        )})
    if any(w in txt_for_style for w in ('昔話', '物語', 'お話をして', '話をして')):
        messages.append({'role': 'developer', 'content': (
            'これは物語の依頼。物語本文に集中する。'
            '締めにNoah自身の感想、余韻、現在の夜や静けさの描写を足さない。'
            '最後は物語内の出来事として自然に閉じる。'
        )})
    if any(w in txt_for_style for w in ('確認したい', 'テストしたい', '検証したい', '試したい', '確認しよう', '見たい')):
        messages.append({'role': 'developer', 'content': (
            'これは作業・検証の文脈。共感だけで終えず、次に確認する観点や手順を1〜3個、自然な文で短く示す。'
            '「心地よい時間」「静かな時間」「心に残る」などの雰囲気締めを足さない。'
        )})
    if __env['detect_question_complaint'](user_input):
        messages.append({'role': 'system', 'content': '対話者が『質問が多い/しつこい/繰り返すな』と示した。ここから数ターンは質問をしない。『話して』『教えて』も言わない。代わりに、短い共感→具体提案（または沈黙）で終える。同じ定型句（いつでも〜、気になること〜）を繰り返さない。'})
    try:
        topics = __env['_load_promoted_topics']()
        hit = __env['_pick_recall_topic'](user_input, topics)
        if hit:
            messages.append({'role': 'developer', 'content': f'もし自然に繋がるなら、過去の定着トピックを“1回だけ”想起してよい。\n- 想起候補: {hit}\n制約: 断定しない/引用しない/重くしない/質問は増やさない。'})
    except Exception:
        pass
    with __env['_conversation_lock']:
        if __env['CONVERSATION_HISTORY']:
            messages.extend(__env['CONVERSATION_HISTORY'])
    is_action_request = False
    try:
        is_action_request = __env['detect_action_request'](user_input)
    except Exception:
        is_action_request = False
    if is_action_request:
        ACTION_FORMAT_RULE = (
            'ユーザーが明示的に「接し方・返し方・断り方・距離感・対応方針」を求めた場合だけ、'
            '短い実用回答にする。通常会話・挨拶・物語依頼・開発の次手確認では、この形式を使わない。'
            '必要なら「方針」「具体」の2段落にしてよいが、見出しを機械的に出しすぎない。'
        )
        messages.append({'role': 'developer', 'content': ACTION_FORMAT_RULE})
        messages.append({'role': 'developer', 'content': '行動やスタンスを聞かれた場合は、会話は短め/確認は1つだけ/境界線を曖昧にしない、など実用的な形に圧縮して返す。'})
    brief = None
    injection = ''
    entity_name = __env['_pick_entity_from_text'](user_input)
    if entity_name:
        brief = __env['get_entity_brief'](entity_name)
        if brief:
            injection = __env['format_brief_for_prompt'](brief)[:700]
            messages.append({'role': 'developer', 'content': injection})
    if __env['DEBUG_INJECTION']:
        print('=== DB injection ===')
        print(injection if injection else '(no brief)')
        print('====================')
    final_user_input = user_input
    messages.append({'role': 'user', 'content': final_user_input})
    return messages
