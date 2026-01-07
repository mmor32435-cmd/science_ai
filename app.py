if user_input and input_mode != "quiz":
    log_activity(st.session_state.user_name, input_mode, user_input)
    st.toast("🧠 Thinking...", icon="🤔")
    
    try:
        role_lang = "Arabic" if language == "العربية" else "English"
        ref = st.session_state.get("ref_text", "")
        student_name = st.session_state.user_name
        student_level = st.session_state.get("student_grade", "General")
        curriculum = st.session_state.get("study_lang", "Arabic")
        
        # تحسين أمر الرسم
        map_instruction = ""
        check_map = ["مخطط", "خريطة", "رسم", "map", "diagram", "chart", "graph"]
        if any(x in str(user_input).lower() for x in check_map):
            map_instruction = """
            URGENT: The user wants a VISUAL DIAGRAM.
            You MUST output Graphviz DOT code.
            Put the code inside: ```dot ... ```
            Example:
            ```dot
            digraph G {
              rankdir=TB;
              node [shape=box, style=filled, fillcolor="#E0E0E0"];
              "Main" -> "Sub1";
              "Main" -> "Sub2";
            }
            ```
            """

        sys_prompt = f"""
        Role: Science Tutor (Mr. Elsayed). Target: {student_level}.
        Curriculum: {curriculum}. Lang: {role_lang}. Name: {student_name}.
        Instructions: Address by name. Adapt to level. Use LaTeX.
        NEVER use itemize/textbf. Use - or *.
        BE CONCISE. 
        {map_instruction}
        Ref: {ref[:20000]}
        """
        
        if input_mode == "image":
             if 'vision' in active_model_name or 'flash' in active_model_name or 'pro' in active_model_name:
                response = model.generate_content([sys_prompt, user_input[0], user_input[1]])
             else: st.error("Model error."); st.stop()
        else:
            response = model.generate_content(f"{sys_prompt}\nInput: {user_input}")
        
        if input_mode != "analysis":
            st.session_state.chat_history.append((str(user_input)[:50], response.text))
        
        st.markdown(f"### 💡 Answer:\n{response.text}")
        
        # 🔥 كود الرسم المحسن جداً 🔥
        try:
            dot_code = None
            # محاولة 1: البحث عن الكود داخل العلامات
            if "```dot" in response.text:
                dot_code = response.text.split("```dot")[1].split("```")[0].strip()
            elif "```graphviz" in response.text:
                dot_code = response.text.split("```graphviz")[1].split("```")[0].strip()
            # محاولة 2: البحث عن بداية ونهاية الكود مباشرة
            elif "digraph" in response.text and "{" in response.text:
                start = response.text.find("digraph")
                end = response.text.rfind("}") + 1
                dot_code = response.text[start:end]

            if dot_code:
                st.graphviz_chart(dot_code)
            
        except Exception as e:
            # لن نظهر خطأ للمستخدم، سنتجاهله
            print(f"Graphviz Error: {e}")

        if input_mode != "analysis":
            audio = asyncio.run(generate_audio_stream(response.text, voice_code))
            st.audio(audio, format='audio/mp3', autoplay=True)
        
    except Exception as e:
        st.error(f"Error: {e}")
