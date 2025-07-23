// main.js - السكريبت الرئيسي للتطبيق

// عند تحميل دوال الصفحة
document.addEventListener("DOMContentLoaded", () => {
    console.log("تم تحميل الصفحة بنجاح، و main.js يعمل!");

    // 1. إخفاء شاشة التحميل بعد انتهاء التحريك (3.1 ثانية)
    const loadingScreen = document.getElementById('loading-screen');
    if (loadingScreen) {
      setTimeout(() => {
        loadingScreen.style.display = 'none';
      }, 3100);
    }

    // 2. التعامل مع رسائل الفلاش (Bootstrap alerts)
    const flashAlerts = document.querySelectorAll('.alert');
    console.log('عدد رسائل الفلاش المكتشفة:', flashAlerts.length);
    flashAlerts.forEach(alert => {
      // تأكد من إضافة فئة show لعرض التنبيه
      if (!alert.classList.contains('show')) {
        alert.classList.add('show');
      }
      // بعد 5 ثواني، بدء الإخفاء والترحيل
      setTimeout(() => {
        alert.classList.remove('show');
        alert.classList.add('fade');
        // إزالة العنصر بعد انتهاء الانتقال
        setTimeout(() => {
          if (alert.parentNode) {
            alert.parentNode.removeChild(alert);
          }
        }, 500);
      }, 5000);
    });

    // 3. تفعيل/إلغاء وضع داكن
    const darkModeToggle = document.getElementById("darkModeToggle");
    if (darkModeToggle) {
      darkModeToggle.addEventListener("click", () => {
        document.body.classList.toggle("dark-mode");
        // حفظ الحالة في LocalStorage
        const isDark = document.body.classList.contains("dark-mode");
        localStorage.setItem("darkMode", isDark ? "enabled" : "disabled");
      });
    }
    // استعادة حالة الوضع الداكن
    if (localStorage.getItem("darkMode") === "enabled") {
      document.body.classList.add("dark-mode");
    }

});

// دالة النسخ للحافظة
function copyToClipboard(button) {
  const input = button.previousElementSibling;
  input.select();
  input.setSelectionRange(0, 99999);
  document.execCommand("copy");
  button.innerText = "✅ تم النسخ";
  setTimeout(() => {
    button.innerText = "📋 نسخ الرابط";
  }, 2000);
}

// تحميل قسم داخل لوحة التحكم بواسطة AJAX
function loadSection(section, pushState = true) {
  const endpoint = "/dashboard/" + section;
  const area = document.getElementById("content-area");
  if (!area) return;

  area.innerHTML = "<div class='loading'>⏳ جاري التحميل...</div>";

  fetch(endpoint)
    .then(response => response.text())
    .then(html => {
      area.innerHTML = html;
      if (pushState) {
        history.pushState({ section }, "", endpoint);
      }
    })
    .catch(err => console.error("Error loading section:", err));
}

// التعامل مع أزرار الرجوع/التقديم في المتصفح
window.onpopstate = event => {
  if (event.state && event.state.section) {
    loadSection(event.state.section, false);
  }
};
