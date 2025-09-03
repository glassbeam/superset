// @ts-nocheck
document.addEventListener('DOMContentLoaded', () => {
  console.log('new instance');
  
  // Dashboard titles
  const TOGGLE_DASHBOARD = 'seemore';
  const TABLE_DASHBOARD = 'popupdashboard';

  // Toggle setup for 'seemore' dashboard
  const setupToggle = () => {
    const gridRows = document.querySelectorAll('.grid-row');
    const toggleLink = document.getElementById('user-content-toggleLink');
    const pageTitle =
      document.querySelector('[data-test="editable-title"]')?.innerText || '';

    console.log('Toggle - Page Title:', pageTitle);
    console.log('Toggle - Grid Rows Found:', gridRows.length);
    gridRows.forEach((row, i) =>
      console.log(`Toggle - Row ${i}:`, row.innerHTML.substring(0, 50) + '...'),
    );
    console.log('Toggle - Toggle Link:', toggleLink);

    if (pageTitle.trim() !== TOGGLE_DASHBOARD) {
      console.log('Toggle - Not the target dashboard. Skipping setup.');
      return false;
    }

    if (gridRows.length >= 3 && toggleLink && !toggleLink.dataset.toggleSetup) {
      console.log('Toggle - Setting up toggle...');
      const chartARow = gridRows[1];
      const chartBRow = gridRows[2];
      const dividerRow = gridRows[0];

      chartARow.style.display = 'block';
      chartBRow.style.display = 'none';
      toggleLink.textContent = 'See More';

      const hasChartA = chartARow.querySelector('[data-test="chart-id-387"]');
      const hasChartB = chartBRow.querySelector('[data-test="chart-id-388"]');
      console.log('Toggle - Chart A in Row 1:', !!hasChartA);
      console.log('Toggle - Chart B in Row 2:', !!hasChartB);

      const toggleCharts = event => {
        event.preventDefault();
        console.log(
          'Toggle - Clicked, chartBRow display:',
          chartBRow.style.display,
        );
        if (
          chartBRow.style.display === 'none' ||
          chartBRow.style.display === ''
        ) {
          chartARow.style.display = 'none';
          chartBRow.style.display = 'block';
          toggleLink.textContent = 'See Less';
        } else {
          chartARow.style.display = 'block';
          chartBRow.style.display = 'none';
          toggleLink.textContent = 'See More';
        }
      };

      toggleLink.removeEventListener('click', toggleLink._toggleHandler);
      toggleLink._toggleHandler = toggleCharts;
      toggleLink.addEventListener('click', toggleLink._toggleHandler);
      toggleLink.dataset.toggleSetup = 'true';
      console.log('Toggle - Event attached to toggleLink');

      const editObserver = new MutationObserver(() => {
        if (document.body.classList.contains('dashboard--editing')) {
          chartARow.style.cssText = '';
          dividerRow.style.cssText = '';
          chartBRow.style.cssText = '';
        }
      });
      editObserver.observe(document.body, { attributes: true });

      console.log('Toggle - Setup complete');
      return true;
    } else {
      console.log('Toggle - Required elements not yet available.');
      return false;
    }
  };

  // Popup setup for 'popupdashboard'
  const setupPopupLinks = () => {
    const pageTitle =
      document.querySelector('[data-test="editable-title"]')?.innerText || '';
    const detailLinks = document.querySelectorAll('.details-link');

    console.log('Popup - Page Title:', pageTitle);
    console.log('Popup - Detail Links Found:', detailLinks.length);
    detailLinks.forEach((link, i) => {
      console.log(`Link ${i}:`, link.outerHTML);
      console.log(`Link ${i} classes:`, link.className);
    });

    if (pageTitle.trim() !== TABLE_DASHBOARD) {
      console.log('Popup - Not the target dashboard. Skipping setup.');
      return false;
    }

    if (detailLinks.length === 0) {
      console.log('Popup - No detail links found yet. Checking table cells...');
      const tableCells = document.querySelectorAll('td');
      tableCells.forEach((cell, i) => {
        console.log(`Cell ${i} content:`, cell.innerHTML);
      });
      return false;
    }

    detailLinks.forEach(link => {
      if (!link.dataset.listenerAdded) {
        link.addEventListener('click', event => {
          event.preventDefault();
          // Get product_code from class name (excluding 'details-link')
          const classes = link.className
            .split(' ')
            .filter(cls => cls !== 'details-link');
          const productCode = classes.length > 0 ? classes[0] : null;
          console.log('Popup - Link clicked:', { productCode });
          if (!productCode) {
            console.error('No product code found in class name.');
            return;
          }
          showPopup(productCode);
        });
        link.dataset.listenerAdded = 'true';
      }
    });

    console.log('Popup - Links setup complete');
    return true;
  };

  const showPopup = productCode => {
    const existingPopup = document.getElementById('chart-popup');
    if (existingPopup) existingPopup.remove();

    // Outer container (like tab-zone)
    const popup = document.createElement('div');
    popup.id = 'chart-popup';
    popup.style.cssText = `
      position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%);
      width: 800px; height: 480px; z-index: 1000;
    `;

    // Margin layer (like tab-zone-margin)
    const marginLayer = document.createElement('div');
    marginLayer.style.cssText = `
      position: absolute; inset: 0; background-color: rgb(255, 255, 255);
      border: 5px solid rgb(227, 233, 243); box-sizing: border-box;
    `;
    popup.appendChild(marginLayer);

    // Padding layer (like tab-zone-padding)
    const paddingLayer = document.createElement('div');
    paddingLayer.style.cssText = `
      position: absolute; inset: 0; padding: 15px;
      display: flex; flex-direction: column;
    `;
    marginLayer.appendChild(paddingLayer);

    // Close button
    const closeBtn = document.createElement('button');
    closeBtn.textContent = 'Close';
    closeBtn.style.cssText = `
      position: absolute; top: 10px; right: 10px; padding: 5px 10px;
      background: #f0f0f0; border: 1px solid rgb(172, 168, 153); border-radius: 3px;
      cursor: pointer; font-size: 12px; color: #333;
    `;
    closeBtn.onclick = () => popup.remove();
    paddingLayer.appendChild(closeBtn);

    // Heading: Product Name (like tab-tvTitle)
    const heading = document.createElement('h2');
    heading.style.cssText = `
      text-align: center; font-size: 16px; font-weight: bold; margin: 0 0 15px 0;
      color: #333; padding-top: 5px;
    `;
    heading.textContent = productCode; // Replace with product_name if available
    paddingLayer.appendChild(heading);

    // First row: Two columns with headings and data
    const textRow = document.createElement('div');
    textRow.style.cssText = `
      display: flex; justify-content: space-between; margin-bottom: 15px;
      height: 80px; background: #f9f9f9; padding: 10px; border: 1px solid rgb(227, 233, 243);
      border-radius: 4px;
    `;

    const column1 = document.createElement('div');
    column1.style.cssText = 'flex: 1; margin-right: 10px; text-align: center;';
    column1.innerHTML = `<strong style="color: #333; font-size: 14px;">Product Code</strong><br><span style="color: #555;">${productCode}</span>`;
    textRow.appendChild(column1);

    const column2 = document.createElement('div');
    column2.style.cssText = 'flex: 1; margin-left: 10px; text-align: center;';
    column2.innerHTML = `<strong style="color: #333; font-size: 14px;">Order Number</strong><br><span style="color: #555;">Loading...</span>`;
    textRow.appendChild(column2);

    paddingLayer.appendChild(textRow);

    // Second row: Chart (like tab-tvView)
    const chartRow = document.createElement('div');
    chartRow.style.cssText = `
      flex: 1; background-color: rgb(255, 255, 255); position: relative;
      border: 1px solid rgb(227, 233, 243); overflow: hidden;
    `;

    // Viewport borders (like tvViewportBorders)
    const viewportBorders = document.createElement('div');
    viewportBorders.style.cssText = `
      position: absolute; inset: 0; pointer-events: none;
    `;
    ['top', 'bottom', 'left', 'right'].forEach(side => {
      const border = document.createElement('div');
      border.style.cssText = `
        position: absolute; background: rgb(227, 233, 243);
        ${side === 'top' || side === 'bottom' ? 'height: 1px; width: 100%;' : 'width: 1px; height: 100%;'}
        ${side}: 0;
      `;
      viewportBorders.appendChild(border);
    });
    chartRow.appendChild(viewportBorders);

    // Chart canvas (like tabCanvas)
    const canvas = document.createElement('canvas');
    canvas.id = 'line-chart';
    canvas.style.cssText = 'display: block;';
    canvas.width = 750;
    canvas.height = 300;
    chartRow.appendChild(canvas);

    paddingLayer.appendChild(chartRow);

    // Separate div for dots in bottom-right corner
    const dotRow = document.createElement('div');
    dotRow.style.cssText = `
      position: absolute; bottom: 15px; right: 15px; display: flex;
      padding: 5px; border: 1px solid rgb(227, 233, 243); border-radius: 4px;
      background: #f9f9f9;
    `;

    const redDot = document.createElement('span');
    redDot.style.cssText = `
      width: 12px; height: 12px; background: red; border-radius: 50%;
      display: inline-block; margin-right: 5px;
    `;
    const redLabel = document.createElement('span');
    redLabel.textContent = 'Critical';
    redLabel.style.cssText = 'font-size: 12px; color: #333;';
    dotRow.appendChild(redDot);
    dotRow.appendChild(redLabel);

    const orangeDot = document.createElement('span');
    orangeDot.style.cssText = `
      width: 12px; height: 12px; background: orange; border-radius: 50%;
      display: inline-block; margin-right: 5px; margin-left: 15px;
    `;
    const orangeLabel = document.createElement('span');
    orangeLabel.textContent = 'Medium';
    orangeLabel.style.cssText = 'font-size: 12px; color: #333;';
    dotRow.appendChild(orangeDot);
    dotRow.appendChild(orangeLabel);

    paddingLayer.appendChild(dotRow);

    document.body.appendChild(popup);

    // Add outside click handler
    const handleOutsideClick = event => {
      if (!popup.contains(event.target)) {
        console.log('Outside click detected, closing popup');
        popup.remove();
        document.removeEventListener('click', handleOutsideClick);
      }
    };

    setTimeout(() => {
      document.removeEventListener('click', handleOutsideClick);
      document.addEventListener('click', handleOutsideClick);
    }, 0);

    const url = 'http://localhost:9000/api/v1/chart/data';
    console.log('Fetching from:', url, 'for product_code:', productCode);

    fetch(url, {
      method: 'POST',
      credentials: 'include',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        datasource: { id: 29, type: 'table' },
        force: false,
        queries: [
          {
            filters: [{ col: 'product_code', op: '==', val: productCode }],
            extras: { having: '', where: '' },
            applied_time_extras: {},
            columns: [
              'order_number',
              'sales',
              'order_date',
              'product_code',
              'details',
            ],
            orderby: [['order_date', false]],
            annotation_layers: [],
            row_limit: 7,
            series_limit: 0,
            order_desc: true,
            url_params: { native_filters_key: 'NGtttdMUhEQ' },
            custom_params: {},
            custom_form_data: {},
            post_processing: [],
            time_offsets: [],
          },
        ],
        form_data: {
          datasource: '29__table',
          viz_type: 'table',
          slice_id: 550,
          url_params: { native_filters_key: 'NGtttdMUhEQ' },
          query_mode: 'raw',
          groupby: [],
          time_grain_sqla: 'P1D',
          temporal_columns_lookup: { order_date: true },
          metrics: [],
          all_columns: [
            'order_number',
            'sales',
            'order_date',
            'product_code',
            'details',
          ],
          percent_metrics: [],
          adhoc_filters: [
            {
              clause: 'WHERE',
              comparator: productCode,
              expressionType: 'SIMPLE',
              operator: '==',
              subject: 'product_code',
            },
          ],
          order_by_cols: [['order_date', false]],
          row_limit: 7,
          server_page_length: 10,
          order_desc: true,
          table_timestamp_format: 'smart_date',
          allow_render_html: true,
          show_cell_bars: true,
          color_pn: true,
          comparison_color_scheme: 'Green',
          comparison_type: 'values',
          dashboards: [14],
          extra_form_data: {},
          chart_id: 550,
          label_colors: {},
          shared_label_colors: [],
          map_label_colors: {},
          extra_filters: [],
          dashboardId: 14,
          force: false,
          result_format: 'json',
          result_type: 'full',
          include_time: false,
        },
        result_format: 'json',
        result_type: 'full',
      }),
    })
      .then(response => {
        console.log('Fetch response:', response);
        if (!response.ok)
          throw new Error(`HTTP error! status: ${response.status}`);
        return response.json();
      })
      .then(data => {
        console.log('Raw data:', data);
        const orderData = data?.result[0]?.data || [];
        console.log('Order data:', orderData);

        if (orderData.length === 0) {
          console.error('No data available for product code:', productCode);
          popup.innerHTML = `<p style="padding: 15px; color: #333; background: rgb(255, 255, 255);">No data available for product code ${productCode}.</p>`;
          popup.appendChild(closeBtn);
          return;
        }

        // Update column2 with the most recent order_number
        const latestOrderNumber = orderData[0].order_number;
        column2.innerHTML = `<strong style="color: #333; font-size: 14px;">Order Number</strong><br><span style="color: #555;">${latestOrderNumber}</span>`;

        const dates = orderData.map(order =>
          new Date(order.order_date).toLocaleDateString(),
        );
        const salesData = orderData.map(order => parseFloat(order.sales));

        // Check for invalid data (0, "NA", null, undefined)
        const hasInvalidSales = salesData.some(
          sales =>
            sales === 0 ||
            String(sales).toLowerCase() === 'na' ||
            sales == null,
        );
        const hasInvalidDates = dates.some(
          date =>
            date === '0' || String(date).toLowerCase() === 'na' || date == null,
        );

        if (hasInvalidSales || hasInvalidDates) {
          const ctx = canvas.getContext('2d');
          ctx.clearRect(0, 0, canvas.width, canvas.height);
          return; // Skip chart drawing, leave div empty
        }

        // Draw line chart using Canvas
        const ctx = canvas.getContext('2d');
        ctx.clearRect(0, 0, canvas.width, canvas.height);

        const leftPadding = 80; // Increased for Y-axis labels
        const padding = 70; // Increased for X-axis visibility
        const chartWidth = canvas.width - leftPadding - padding;
        const chartHeight = canvas.height - 2 * padding;
        const maxSales = Math.max(...salesData);
        const minSales = Math.min(...salesData);
        const salesRange = maxSales - minSales || 1;

        // Draw axes
        ctx.beginPath();
        ctx.moveTo(leftPadding, padding);
        ctx.lineTo(leftPadding, canvas.height - padding);
        ctx.lineTo(canvas.width - padding, canvas.height - padding);
        ctx.strokeStyle = '#000';
        ctx.stroke();

        // X-axis labels (dates)
        ctx.textAlign = 'center';
        ctx.fillStyle = '#000';
        ctx.font = '12px Arial';
        const xStep = chartWidth / (dates.length - 1);
        dates.forEach((date, index) => {
          const x = leftPadding + index * xStep;
          ctx.fillText(date, x, canvas.height - padding + 20);
        });

        // X-axis label: "Date"
        ctx.fillText(
          'Date',
          (leftPadding + canvas.width - padding) / 2,
          canvas.height - padding + 40,
        );

        // Y-axis labels (sales)
        ctx.textAlign = 'right';
        ctx.font = '11px Arial'; // Slightly smaller for clarity
        const ySteps = 5;
        const yStepValue = salesRange / ySteps;
        for (let i = 0; i <= ySteps; i++) {
          const salesValue = minSales + i * yStepValue;
          const y = canvas.height - padding - (i * chartHeight) / ySteps;
          ctx.fillText(salesValue.toFixed(2), leftPadding - 5, y + 4);
        }

        // Y-axis subtitle: productCode
        ctx.save();
        ctx.translate(leftPadding - 60, canvas.height / 2);
        ctx.rotate(-Math.PI / 2);
        ctx.textAlign = 'center';
        ctx.font = '10px Arial';
        ctx.fillText(`(${productCode})`, 0, 0);
        ctx.restore();

        // Draw line (dark blue)
        ctx.beginPath();
        ctx.strokeStyle = '#5c749f'; // Dark blue
        ctx.lineWidth = 2;
        const linePoints = [];
        salesData.forEach((sales, index) => {
          const x = leftPadding + index * xStep;
          const y =
            canvas.height -
            padding -
            ((sales - minSales) / salesRange) * chartHeight;
          linePoints.push({ x, y });
          if (index === 0) {
            ctx.moveTo(x, y);
          } else {
            ctx.lineTo(x, y);
          }
        });
        ctx.stroke();

        // Chart title
        ctx.textAlign = 'center';
        ctx.font = '12px Arial';
        ctx.fillText(
          `Sales over Time for ${productCode}`,
          (leftPadding + canvas.width - padding) / 2,
          padding / 2,
        );

        // Track current highlighted index
        let currentHighlightIndex = -1;

        // Add hover behavior
        let popover = null;
        canvas.addEventListener('mousemove', event => {
          const rect = canvas.getBoundingClientRect();
          const mouseX = event.clientX - rect.left;
          const mouseY = event.clientY - rect.top;

          // Redraw chart to remove previous highlight
          ctx.clearRect(0, 0, canvas.width, canvas.height);
          ctx.beginPath();
          ctx.moveTo(leftPadding, padding);
          ctx.lineTo(leftPadding, canvas.height - padding);
          ctx.lineTo(canvas.width - padding, canvas.height - padding);
          ctx.strokeStyle = '#000';
          ctx.stroke();
          ctx.textAlign = 'center';
          ctx.fillStyle = '#000';
          ctx.font = '12px Arial';
          dates.forEach((date, index) => {
            const x = leftPadding + index * xStep;
            ctx.fillText(date, x, canvas.height - padding + 20);
          });
          ctx.fillText(
            'Date',
            (leftPadding + canvas.width - padding) / 2,
            canvas.height - padding + 40,
          );
          ctx.textAlign = 'right';
          ctx.font = '11px Arial';
          for (let i = 0; i <= ySteps; i++) {
            const salesValue = minSales + i * yStepValue;
            const y = canvas.height - padding - (i * chartHeight) / ySteps;
            ctx.fillText(salesValue.toFixed(2), leftPadding - 5, y + 4);
          }
          ctx.save();
          ctx.translate(leftPadding - 60, canvas.height / 2);
          ctx.rotate(-Math.PI / 2);
          ctx.textAlign = 'center';
          ctx.font = '10px Arial';
          ctx.fillText(`(${productCode})`, 0, 0);
          ctx.restore();
          ctx.beginPath();
          ctx.strokeStyle = '#5c749f';
          ctx.lineWidth = 2;
          linePoints.forEach((point, index) => {
            if (index === 0) {
              ctx.moveTo(point.x, point.y);
            } else {
              ctx.lineTo(point.x, point.y);
            }
          });
          ctx.stroke();
          ctx.textAlign = 'center';
          ctx.font = '12px Arial';
          ctx.fillText(
            `Sales over Time for ${productCode}`,
            (leftPadding + canvas.width - padding) / 2,
            padding / 2,
          );

          // Find nearest point or line segment
          let closestIndex = -1;
          let minDistance = 10; // Tolerance of 10px
          for (let i = 0; i < linePoints.length; i++) {
            const point = linePoints[i];
            const dx = mouseX - point.x;
            const dy = mouseY - point.y;
            const distance = Math.sqrt(dx * dx + dy * dy);
            if (distance < minDistance) {
              minDistance = distance;
              closestIndex = i;
            }
          }

          let highlightIndex = -1;
          if (closestIndex !== -1 && minDistance <= 10) {
            // Hovering near a point
            highlightIndex = closestIndex;
          } else {
            // Check if on a line segment (between points)
            for (let i = 0; i < linePoints.length - 1; i++) {
              const p1 = linePoints[i];
              const p2 = linePoints[i + 1];
              const d = distanceToSegment(
                mouseX,
                mouseY,
                p1.x,
                p1.y,
                p2.x,
                p2.y,
              );
              if (d < 10) {
                highlightIndex = i; // Highlight previous breakpoint
                break;
              }
            }
          }

          if (popover) popover.remove();
          if (highlightIndex === -1) {
            return; // No highlight or popover
          }

          const point = linePoints[highlightIndex];
          const currentSales = salesData[highlightIndex];
          const prevSales =
            highlightIndex > 0 ? salesData[highlightIndex - 1] : null;
          const date = dates[highlightIndex];

          popover = document.createElement('div');
          popover.style.cssText = `
            position: absolute; background: white; border: 1px solid #ccc;
            padding: 5px; font-size: 12px; border-radius: 3px; pointer-events: none;
            z-index: 1001; box-shadow: 0 4px 8px rgba(0,0,0,0.2);
            max-height: 80px; overflow-y: auto;
          `;

          // Fixed 100px below offset
          const topOffset = 80;
          let topPos = point.y + topOffset;
          const popupRect = popup.getBoundingClientRect();
          const popoverHeight = 60;

          if (topPos < popupRect.top + 15) {
            topPos = popupRect.top + 15;
          }
          if (topPos + popoverHeight > popupRect.bottom - 15) {
            topPos = popupRect.bottom - 15 - popoverHeight;
          }

          popover.style.top = `${topPos}px`;
          popover.style.left = `${point.x + 10}px`;

          if (parseInt(popover.style.left) + 100 > popupRect.right - 15) {
            popover.style.left = `${popupRect.right - 15 - 100}px`;
          }

          popover.innerHTML = `
            <strong>Date:</strong> ${date}<br>
            <strong>Current Sales:</strong> ${currentSales.toFixed(2)}<br>
            <strong>Previous Sales:</strong> ${prevSales ? prevSales.toFixed(2) : 'N/A'}
          `;
          popup.appendChild(popover);

          // Highlight the point
          ctx.beginPath();
          ctx.arc(point.x, point.y, 5, 0, Math.PI * 2);
          ctx.fillStyle = '#5c749f';
          ctx.fill();
          ctx.lineWidth = 1;
          ctx.strokeStyle = '#fff';
          ctx.stroke();

          // Update current highlight
          currentHighlightIndex = highlightIndex;
        });

        canvas.addEventListener('mouseleave', () => {
          if (popover) {
            popover.remove();
            popover = null;
          }
          if (currentHighlightIndex !== -1) {
            // Redraw without highlight
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ctx.beginPath();
            ctx.moveTo(leftPadding, padding);
            ctx.lineTo(leftPadding, canvas.height - padding);
            ctx.lineTo(canvas.width - padding, canvas.height - padding);
            ctx.strokeStyle = '#000';
            ctx.stroke();
            ctx.textAlign = 'center';
            ctx.fillStyle = '#000';
            ctx.font = '12px Arial';
            dates.forEach((date, index) => {
              const x = leftPadding + index * xStep;
              ctx.fillText(date, x, canvas.height - padding + 20);
            });
            ctx.fillText(
              'Date',
              (leftPadding + canvas.width - padding) / 2,
              canvas.height - padding + 40,
            );
            ctx.textAlign = 'right';
            ctx.font = '11px Arial';
            for (let i = 0; i <= ySteps; i++) {
              const salesValue = minSales + i * yStepValue;
              const y = canvas.height - padding - (i * chartHeight) / ySteps;
              ctx.fillText(salesValue.toFixed(2), leftPadding - 5, y + 4);
            }
            ctx.save();
            ctx.translate(leftPadding - 60, canvas.height / 2);
            ctx.rotate(-Math.PI / 2);
            ctx.textAlign = 'center';
            ctx.font = '10px Arial';
            ctx.fillText(`(${productCode})`, 0, 0);
            ctx.restore();
            ctx.beginPath();
            ctx.strokeStyle = '#5c749f';
            ctx.lineWidth = 2;
            linePoints.forEach((point, index) => {
              if (index === 0) {
                ctx.moveTo(point.x, point.y);
              } else {
                ctx.lineTo(point.x, point.y);
              }
            });
            ctx.stroke();
            ctx.textAlign = 'center';
            ctx.font = '12px Arial';
            ctx.fillText(
              `Sales over Time for ${productCode}`,
              (leftPadding + canvas.width - padding) / 2,
              padding / 2,
            );
            currentHighlightIndex = -1;
          }
        });

        // Helper function to calculate distance from point to line segment
        function distanceToSegment(px, py, x1, y1, x2, y2) {
          const l2 = (x2 - x1) * (x2 - x1) + (y2 - y1) * (y2 - y1);
          if (l2 === 0)
            return Math.sqrt((px - x1) * (px - x1) + (py - y1) * (py - y1));
          let t = ((px - x1) * (x2 - x1) + (py - y1) * (y2 - y1)) / l2;
          t = Math.max(0, Math.min(1, t));
          const projX = x1 + t * (x2 - x1);
          const projY = y1 + t * (y2 - y1);
          return Math.sqrt(
            (px - projX) * (px - projX) + (py - projY) * (py - projY),
          );
        }
      })
      .then(() => {
        // Stop propagation of clicks inside the popup
        popup.addEventListener('click', event => {
          event.stopPropagation();
        });
      })
      .catch(error => {
        console.error('Fetch error:', error);
        popup.innerHTML = `<p style="padding: 15px; color: #333; background: rgb(255, 255, 255);">Error loading data: ${error.message}</p>`;
        popup.appendChild(closeBtn);
      });
  };

  // Single MutationObserver for both features
  const observer = new MutationObserver(() => {
    setupToggle();
    setupPopupLinks();
  });

  observer.observe(document.body, { childList: true, subtree: true });

  // Initial attempts
  setupToggle();
  setupPopupLinks();
});

