// Sticky Header & About Section Animation
window.addEventListener('scroll', function () {
    const header = document.querySelector('header');
    header.classList.toggle('sticky', window.scrollY > 0);

    // About section animation
    const aboutImage = document.querySelector('.about-image');
    const aboutText = document.querySelector('.about-text');

    if (aboutImage && aboutText) {
        const aboutSection = document.querySelector('.about-section');
        const aboutSectionTop = aboutSection.getBoundingClientRect().top;
        const windowHeight = window.innerHeight;

        if (aboutSectionTop < windowHeight - 100) {
            aboutImage.classList.add('visible');
            aboutText.classList.add('visible');
        }
    }
});

// Initialize about section animations on page load
window.addEventListener('load', function () {
    window.dispatchEvent(new Event('scroll'));
});

// Mobile Menu Toggle
document.querySelector('.toggle').addEventListener('click', function () {
    this.classList.toggle('active');
    document.querySelector('.menu').classList.toggle('active');
});

// Image Slider with Zoom Effect
const slides = document.querySelectorAll('.slide');
let currentSlide = 0;

function changeSlide() {
    slides.forEach(slide => slide.classList.remove('active'));
    currentSlide = (currentSlide + 1) % slides.length;
    slides[currentSlide].classList.add('active');
}

// Change slide every 6 seconds
setInterval(changeSlide, 6000);

// Smooth Scrolling for Anchor Links
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
        e.preventDefault();

        const targetId = this.getAttribute('href');
        if (targetId === '#') return;

        const targetElement = document.querySelector(targetId);
        if (targetElement) {
            // Close mobile menu if open
            document.querySelector('.menu').classList.remove('active');
            document.querySelector('.toggle').classList.remove('active');

            // Scroll to target
            window.scrollTo({
                top: targetElement.offsetTop - 80,
                behavior: 'smooth'
            });

            // Update active menu item
            document.querySelectorAll('.menu li a').forEach(item => {
                item.classList.remove('active');
            });
            this.classList.add('active');
        }
    });
});

// Navigation Menu Active State
document.addEventListener('DOMContentLoaded', function () {
    const menuLinks = document.querySelectorAll('.menu li a');
    const sections = document.querySelectorAll('section[id]');

    function setActiveLink() {
        const scrollY = window.scrollY;

        sections.forEach(section => {
            const sectionHeight = section.offsetHeight;
            const sectionTop = section.offsetTop - 100;
            const sectionId = section.getAttribute('id');

            if (scrollY > sectionTop && scrollY <= sectionTop + sectionHeight) {
                menuLinks.forEach(link => {
                    link.classList.remove('active');
                    if (link.getAttribute('href') === '#' + sectionId) {
                        link.classList.add('active');
                    }
                });
            }
        });
    }

    window.addEventListener('scroll', setActiveLink);

    // Smooth scrolling and active state handling
    menuLinks.forEach(link => {
        link.addEventListener('click', function (e) {
            e.preventDefault();

            const targetId = this.getAttribute('href');
            const targetSection = document.querySelector(targetId);

            if (targetSection) {
                // Scroll to the target section
                window.scrollTo({
                    top: targetSection.offsetTop - 80,
                    behavior: 'smooth'
                });

                // Close mobile menu if open
                const menu = document.querySelector('.menu');
                const toggle = document.querySelector('.toggle');
                if (menu.classList.contains('active')) {
                    menu.classList.remove('active');
                    toggle.classList.remove('active');
                }

                // Set active class
                menuLinks.forEach(link => link.classList.remove('active'));
                this.classList.add('active');
            }
        });
    });
});

// Event Filter Buttons
document.addEventListener('DOMContentLoaded', () => {
    const filterButtons = document.querySelectorAll('.filter-btn');
    const eventCards = document.querySelectorAll('.event-card');

    filterButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            filterButtons.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            const selectedType = btn.getAttribute('data-type');

            eventCards.forEach(card => {
                const cardType = card.getAttribute('data-type');
                card.style.display = (selectedType === 'all' || cardType === selectedType) ? 'block' : 'none';
            });
        });
    });
});

// Gallery Filter Buttons
document.addEventListener('DOMContentLoaded', function () {
    const galleryFilterBtns = document.querySelectorAll('.gallery-filter-btn');
    const galleryItems = document.querySelectorAll('.gallery-item');

    galleryFilterBtns.forEach(btn => {
        btn.addEventListener('click', function () {
            galleryFilterBtns.forEach(b => b.classList.remove('active'));
            this.classList.add('active');

            const category = this.getAttribute('data-category');

            galleryItems.forEach(item => {
                item.style.display = (category === 'all' || item.getAttribute('data-category') === category) ? 'block' : 'none';
            });
        });
    });
});
