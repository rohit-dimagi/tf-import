# __generated__ by Terraform
# Please review these resources and move them into your main configuration files.

# __generated__ by Terraform
resource "aws_lb_listener" "elb-iac-june-80" {
  load_balancer_arn = "arn:aws:elasticloadbalancing:eu-west-1:1234:loadbalancer/app/elb-iac-june/34fdjubngsold"
  port              = 80
  protocol          = "HTTP"
  default_action {
    order            = 1
    target_group_arn = "arn:aws:elasticloadbalancing:eu-west-1:1234:targetgroup/testing-IAC-june/34fdjubngsold"
    type             = "forward"
    forward {
      stickiness {
        duration = 3600
        enabled  = false
      }
      target_group {
        arn    = "arn:aws:elasticloadbalancing:eu-west-1:1234:targetgroup/testing-IAC-june/34fdjubngsold"
        weight = 1
      }
    }
  }
}

# __generated__ by Terraform
resource "aws_lb_target_group" "testing-IAC-june-80" {
  deregistration_delay              = jsonencode(300)
  ip_address_type                   = "ipv4"
  load_balancing_algorithm_type     = "round_robin"
  load_balancing_anomaly_mitigation = "off"
  load_balancing_cross_zone_enabled = "use_load_balancer_configuration"
  name                              = "testing-IAC-june"
  port                              = 80
  protocol                          = "HTTP"
  protocol_version                  = "HTTP1"
  slow_start                        = 0
  tags = {
    name = "manul-tag"
  }
  tags_all = {
    name = "manul-tag"
  }
  target_type = "instance"
  vpc_id      = "vpc-34fdjubngsold"
  health_check {
    enabled             = true
    healthy_threshold   = 5
    interval            = 30
    matcher             = "200-399"
    path                = "/"
    port                = "traffic-port"
    protocol            = "HTTP"
    timeout             = 5
    unhealthy_threshold = 2
  }
  stickiness {
    cookie_duration = 86400
    enabled         = false
    type            = "lb_cookie"
  }
  target_failover {
  }
  target_health_state {
  }
}

# __generated__ by Terraform
resource "aws_lb" "elb-iac-june" {
  client_keep_alive                           = 3600
  desync_mitigation_mode                      = "defensive"
  drop_invalid_header_fields                  = false
  enable_cross_zone_load_balancing            = true
  enable_deletion_protection                  = false
  enable_http2                                = true
  enable_tls_version_and_cipher_suite_headers = false
  enable_waf_fail_open                        = false
  enable_xff_client_port                      = false
  idle_timeout                                = 60
  internal                                    = true
  ip_address_type                             = "ipv4"
  load_balancer_type                          = "application"
  name                                        = "elb-iac-june"
  preserve_host_header                        = false
  security_groups                             = ["sg-34fdjubngsold"]
  xff_header_processing_mode                  = "append"
  access_logs {
    bucket  = ""
    enabled = false
  }
  connection_logs {
    bucket  = ""
    enabled = false
  }
  subnet_mapping {
    subnet_id = "subnet-34fdjubngsold"
  }
  subnet_mapping {
    subnet_id = "subnet-34fdjubngsold"
  }
  subnet_mapping {
    subnet_id = "subnet-34fdjubngsold"
  }
}
