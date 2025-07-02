"""Enhanced JavaScript detection for determining scraping strategy."""

import re
from typing import Dict, List, Set
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup


class JavaScriptDetector:
    """Detects JavaScript-heavy pages that require dynamic rendering."""
    
    # Common SPA framework indicators
    SPA_FRAMEWORKS = {
        'react': [
            r'react\.js',
            r'react\.min\.js', 
            r'react-dom',
            r'ReactDOM\.render',
            r'React\.createElement',
            r'<div[^>]+id=["\']root["\']',
            r'<div[^>]+id=["\']app["\']',
        ],
        'vue': [
            r'vue\.js',
            r'vue\.min\.js',
            r'new Vue\(',
            r'Vue\.component',
            r'<div[^>]+id=["\']app["\']',
            r'v-if|v-for|v-model',
        ],
        'angular': [
            r'angular\.js',
            r'angular\.min\.js',
            r'ng-app',
            r'ng-controller',
            r'angular\.module',
            r'\[ng-\w+\]',
        ],
        'svelte': [
            r'svelte',
            r'_svelte',
        ],
        'ember': [
            r'ember\.js',
            r'ember\.min\.js',
            r'Ember\.Application',
        ]
    }
    
    # Common AJAX/dynamic loading patterns
    AJAX_PATTERNS = [
        r'XMLHttpRequest',
        r'fetch\(',
        r'axios\.',
        r'$.ajax',
        r'$.get|$.post',
        r'async\s+function',
        r'await\s+fetch',
    ]
    
    # DOM manipulation libraries
    DOM_MANIPULATION = [
        r'jQuery',
        r'\$\(',
        r'document\.createElement',
        r'document\.appendChild',
        r'innerHTML\s*=',
        r'textContent\s*=',
    ]
    
    # Loading/skeleton patterns  
    LOADING_INDICATORS = [
        r'loading',
        r'spinner',
        r'skeleton',
        r'placeholder',
        r'data-loading',
        r'is-loading',
    ]

    def __init__(self):
        """Initialize the detector."""
        self.confidence_threshold = 0.6  # Threshold for JS detection
        
    def detect_javascript_need(self, html: str, url: str = "") -> Dict[str, any]:
        """
        Analyze HTML to determine if JavaScript rendering is needed.
        
        Args:
            html: Raw HTML content
            url: Source URL for additional context
            
        Returns:
            Dict with detection results including confidence score and reasons
        """
        soup = BeautifulSoup(html, 'lxml')
        
        # Initialize scoring
        js_indicators = {
            'spa_framework': 0,
            'empty_containers': 0,
            'ajax_patterns': 0,
            'dom_manipulation': 0,
            'loading_indicators': 0,
            'script_complexity': 0,
            'content_ratio': 0,
        }
        
        reasons = []
        
        # 1. Check for SPA frameworks
        framework_score, framework_reasons = self._check_spa_frameworks(html)
        js_indicators['spa_framework'] = framework_score
        reasons.extend(framework_reasons)
        
        # 2. Check for empty containers that might be populated by JS
        container_score, container_reasons = self._check_empty_containers(soup)
        js_indicators['empty_containers'] = container_score
        reasons.extend(container_reasons)
        
        # 3. Check for AJAX patterns
        ajax_score, ajax_reasons = self._check_ajax_patterns(html)
        js_indicators['ajax_patterns'] = ajax_score  
        reasons.extend(ajax_reasons)
        
        # 4. Check DOM manipulation
        dom_score, dom_reasons = self._check_dom_manipulation(html)
        js_indicators['dom_manipulation'] = dom_score
        reasons.extend(dom_reasons)
        
        # 5. Check for loading indicators
        loading_score, loading_reasons = self._check_loading_indicators(soup)
        js_indicators['loading_indicators'] = loading_score
        reasons.extend(loading_reasons)
        
        # 6. Analyze script complexity
        script_score, script_reasons = self._analyze_script_complexity(soup)
        js_indicators['script_complexity'] = script_score
        reasons.extend(script_reasons)
        
        # 7. Check content ratio (text vs scripts)
        content_score, content_reasons = self._check_content_ratio(soup)
        js_indicators['content_ratio'] = content_score
        reasons.extend(content_reasons)
        
        # Calculate overall confidence
        # Weight the scores based on importance
        weights = {
            'spa_framework': 0.3,
            'empty_containers': 0.25,
            'ajax_patterns': 0.15,
            'dom_manipulation': 0.1,
            'loading_indicators': 0.1,
            'script_complexity': 0.05,
            'content_ratio': 0.05,
        }
        
        confidence = sum(
            js_indicators[key] * weights[key] 
            for key in weights
        )
        
        needs_js = confidence >= self.confidence_threshold
        
        return {
            'needs_javascript': needs_js,
            'confidence': min(confidence, 1.0),
            'indicators': js_indicators,
            'reasons': reasons,
            'recommendation': 'dynamic' if needs_js else 'static'
        }
    
    def _check_spa_frameworks(self, html: str) -> tuple[float, List[str]]:
        """Check for Single Page Application frameworks."""
        reasons = []
        max_score = 0
        
        for framework, patterns in self.SPA_FRAMEWORKS.items():
            matches = 0
            for pattern in patterns:
                if re.search(pattern, html, re.IGNORECASE):
                    matches += 1
                    reasons.append(f"Found {framework} pattern: {pattern}")
            
            if matches > 0:
                framework_score = min(matches / len(patterns), 1.0)
                max_score = max(max_score, framework_score)
        
        return max_score, reasons
    
    def _check_empty_containers(self, soup: BeautifulSoup) -> tuple[float, List[str]]:
        """Check for empty containers that JS might populate."""
        reasons = []
        empty_containers = 0
        total_containers = 0
        
        # Common container patterns
        container_selectors = [
            'div#root',
            'div#app', 
            'div[class*="app"]',
            'div[class*="container"]',
            'main',
            'section',
        ]
        
        for selector in container_selectors:
            containers = soup.select(selector)
            for container in containers:
                total_containers += 1
                # Check if container is essentially empty
                text_content = container.get_text(strip=True)
                child_elements = len(container.find_all())
                
                if len(text_content) < 50 and child_elements < 3:
                    empty_containers += 1
                    reasons.append(f"Empty container found: {selector}")
        
        if total_containers == 0:
            return 0, reasons
            
        ratio = empty_containers / total_containers
        return min(ratio * 2, 1.0), reasons  # Amplify the signal
    
    def _check_ajax_patterns(self, html: str) -> tuple[float, List[str]]:
        """Check for AJAX/fetch patterns in scripts."""
        reasons = []
        matches = 0
        
        for pattern in self.AJAX_PATTERNS:
            if re.search(pattern, html, re.IGNORECASE):
                matches += 1
                reasons.append(f"AJAX pattern found: {pattern}")
        
        score = min(matches / len(self.AJAX_PATTERNS), 1.0)
        return score, reasons
    
    def _check_dom_manipulation(self, html: str) -> tuple[float, List[str]]:
        """Check for DOM manipulation patterns."""
        reasons = []
        matches = 0
        
        for pattern in self.DOM_MANIPULATION:
            if re.search(pattern, html, re.IGNORECASE):
                matches += 1
                reasons.append(f"DOM manipulation pattern: {pattern}")
        
        score = min(matches / len(self.DOM_MANIPULATION), 1.0)
        return score, reasons
    
    def _check_loading_indicators(self, soup: BeautifulSoup) -> tuple[float, List[str]]:
        """Check for loading/placeholder elements."""
        reasons = []
        loading_elements = 0
        
        for pattern in self.LOADING_INDICATORS:
            # Check in class names
            elements = soup.find_all(attrs={'class': re.compile(pattern, re.I)})
            loading_elements += len(elements)
            
            # Check in data attributes
            elements = soup.find_all(attrs={re.compile(f'data-{pattern}', re.I): True})
            loading_elements += len(elements)
            
            if elements:
                reasons.append(f"Loading indicator found: {pattern}")
        
        # Normalize score
        score = min(loading_elements / 10, 1.0)  # Cap at 10 indicators
        return score, reasons
    
    def _analyze_script_complexity(self, soup: BeautifulSoup) -> tuple[float, List[str]]:
        """Analyze the complexity of JavaScript code."""
        reasons = []
        script_tags = soup.find_all('script')
        
        if not script_tags:
            return 0, reasons
        
        total_js_length = 0
        complex_patterns = 0
        
        complexity_indicators = [
            r'import\s+',
            r'export\s+',
            r'require\(',
            r'module\.exports',
            r'class\s+\w+',
            r'function\*',
            r'=>',  # Arrow functions
            r'async\s+function',
        ]
        
        for script in script_tags:
            if script.string:
                script_content = script.string
                total_js_length += len(script_content)
                
                for pattern in complexity_indicators:
                    if re.search(pattern, script_content):
                        complex_patterns += 1
        
        if total_js_length > 5000:  # Significant amount of JS
            reasons.append(f"Large JavaScript codebase: {total_js_length} chars")
        
        if complex_patterns > 3:
            reasons.append(f"Complex JS patterns found: {complex_patterns}")
        
        # Score based on both size and complexity
        size_score = min(total_js_length / 20000, 0.5)  # Max 0.5 for size
        complexity_score = min(complex_patterns / 10, 0.5)  # Max 0.5 for complexity
        
        return size_score + complexity_score, reasons
    
    def _check_content_ratio(self, soup: BeautifulSoup) -> tuple[float, List[str]]:
        """Check ratio of visible content vs scripts."""
        reasons = []
        
        # Get visible text content
        visible_text = soup.get_text(strip=True)
        visible_length = len(visible_text)
        
        # Get script content
        scripts = soup.find_all('script')
        script_length = sum(len(script.get_text()) for script in scripts if script.string)
        
        if visible_length == 0 and script_length > 0:
            reasons.append("No visible content, only scripts")
            return 1.0, reasons
        
        if visible_length == 0:
            return 0, reasons
        
        script_ratio = script_length / (visible_length + script_length)
        
        if script_ratio > 0.3:  # More than 30% scripts
            reasons.append(f"High script-to-content ratio: {script_ratio:.2f}")
            return script_ratio, reasons
        
        return 0, reasons 