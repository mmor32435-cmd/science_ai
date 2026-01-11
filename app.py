# ------------------- استبدل كتلة النموذج الحالية بهذه -------------------
with col2:
    st.info(random.choice(DAILY_FACTS))
    with st.form("login_form"):
        name = st.text_input("الاسم:")
        grade = st.selectbox("الصف:", ["الرابع", "الخامس", "السادس", "الأول ع", "الثاني ع", "الثالث ع", "ثانوي", "Other"])
        code = st.text_input("الكود:", type="password")
        remember = st.checkbox("تذكرني على هذا الجهاز")
        if st.form_submit_button("دخول"):
            db_code = safe_get_control_sheet_value()
            is_teacher = (code == TEACHER_MASTER_KEY)
            is_student = (db_code and code == db_code) or (not db_code and code == TEACHER_MASTER_KEY)  # fallback
            if is_teacher or is_student:
                st.session_state.auth_status = True
                st.session_state.user_type = "teacher" if is_teacher else "student"
                st.session_state.user_name = name if is_student else "Mr. Elsayed"
                st.session_state.student_grade = grade
                st.session_state.start_time = time.time()
                st.session_state.current_xp = 0 if not is_student else st.session_state.get("current_xp", 0)
                log_login(st.session_state.user_name, "teacher" if is_teacher else "student", grade)
                st.success("تم الدخول!")
                # بدلاً من الاستدعاء المباشر لإعادة التشغيل داخل الفورم، نضع علامة ثم نغادر الفورم
                st.session_state["_needs_rerun"] = True
            else:
                st.error("الكود غير صحيح")

    # بعد إغلاق كتلة الـ form: إذا وُجدت العلامة، نفّذ إعادة التشغيل من السياق الرئيسي
    if st.session_state.pop("_needs_rerun", False):
        time.sleep(0.4)
        st.experimental_rerun()
# -----------------------------------------------------------------------
